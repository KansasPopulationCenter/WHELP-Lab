import os

from pathlib import Path
import json, sys, time
import numpy as np

scratch = Path(sys.argv[1])
ahn = Path(os.environ["WH_AHN_ROOT"]).expanduser().resolve()
import duckdb

c = duckdb.connect(str(scratch / "ahn_work.duckdb"), config={"threads":6,"memory_limit":"6GB"})
c.execute("SET preserve_insertion_order=false")
c.execute("SET temp_directory=?", [str(scratch / "spill_ahn")])
source = (ahn / "Aim1_Postpartum_Heat" / "data" / "aim1-Joseph.duckdb").as_posix()
c.execute(f"ATTACH '{source}' AS a (READ_ONLY)")

def build(name, query):
    started = time.monotonic()
    c.execute(f"CREATE OR REPLACE TABLE {name} AS {query}")
    n = c.execute(f"SELECT count(*) FROM {name}").fetchone()[0]
    print(name, n, round(time.monotonic()-started,1), "seconds",flush=True)
    return n

def agegroup(expression):
    return f"""CASE WHEN {expression} BETWEEN 18 AND 24 THEN 18 WHEN {expression} BETWEEN 25 AND 29 THEN 25
                    WHEN {expression} BETWEEN 30 AND 34 THEN 30 WHEN {expression} BETWEEN 35 AND 39 THEN 35
                    WHEN {expression} BETWEEN 40 AND 49 THEN 40 END"""

pool = build("birth_pool", """
WITH first_delivery AS (
    SELECT d.*, birth.year_of_birth,
           row_number() OVER (PARTITION BY d.hvid ORDER BY d.admit,d.delivery_id) AS delivery_order
    FROM a.delivery_covariates d JOIN a.cohort birth USING(delivery_id)
)
SELECT * EXCLUDE(delivery_order) FROM first_delivery
WHERE delivery_order=1 AND year(admit) IN (2023,2024)
  AND ga_recorded AND ga_weeks BETWEEN 22 AND 42 AND state IS NOT NULL
  AND year(admit)-year_of_birth BETWEEN 18 AND 49
""")
case_age = agegroup("year(b.pregnancy_start)-b.year_of_birth")
case_count = build("case_pool", f"""
WITH covered AS (
    SELECT b.*, b.pregnancy_start AS idx, date_trunc('month',b.pregnancy_start)::DATE AS month,
           {case_age} AS age_band
    FROM birth_pool b
    WHERE year(b.admit)=2023
      AND b.pregnancy_start-449>=DATE '2021-01-01'
      AND EXISTS (
        SELECT 1 FROM a.medical_spans s
        WHERE s.hvid=b.hvid AND s.span_start<=b.pregnancy_start-449 AND s.span_end>=b.discharge
      )
)
SELECT b.*, min(e.pay_type) AS index_payer
FROM covered b JOIN a.enrollment e ON b.hvid=e.hvid AND e.benefit_type='MEDICAL'
    AND b.idx BETWEEN e.date_start AND e.date_end
WHERE age_band IS NOT NULL
GROUP BY ALL
HAVING count(DISTINCT e.pay_type)=1 AND min(e.pay_type) IN ('COMMERCIAL','MANAGED MEDICAID')
""")
control_age = agegroup("year(m.month)-b.year_of_birth")
control_count = build("control_pool",f"""
WITH months AS (SELECT DISTINCT month FROM case_pool),
covered AS (
    SELECT b.*, m.month, {control_age} AS age_band
    FROM birth_pool b CROSS JOIN months m
    WHERE year(b.admit)=2024
      AND b.pregnancy_start>last_day(m.month)+139
      AND EXISTS (
        SELECT 1 FROM a.medical_spans s
        WHERE s.hvid=b.hvid AND s.span_start<=m.month-449 AND s.span_end>=last_day(m.month)+139
      )
), indexed AS (
    SELECT b.*, min(e.pay_type) AS index_payer
    FROM covered b JOIN a.enrollment e ON b.hvid=e.hvid AND e.benefit_type='MEDICAL'
        AND b.month BETWEEN e.date_start AND e.date_end
    WHERE age_band IS NOT NULL
    GROUP BY ALL
    HAVING count(DISTINCT e.pay_type)=1 AND min(e.pay_type) IN ('COMMERCIAL','MANAGED MEDICAID')
), available AS (
    SELECT i.* FROM indexed i
    SEMI JOIN case_pool c USING(month,state,age_band,index_payer)
)
SELECT * FROM available QUALIFY row_number() OVER (PARTITION BY hvid ORDER BY hash(hvid,month),month)=1
""")
pair_count = build("pairs", """
WITH cases AS (
    SELECT *, row_number() OVER (PARTITION BY month,state,age_band,index_payer ORDER BY hash(hvid),hvid) AS slot
    FROM case_pool
), controls AS (
    SELECT *, row_number() OVER (PARTITION BY month,state,age_band,index_payer ORDER BY hash(hvid),hvid) AS slot
    FROM control_pool
)
SELECT c.delivery_id AS pair_id,c.hvid AS case_hvid,k.hvid AS control_hvid,c.idx,c.month,c.state,c.age_band,
       c.index_payer,c.admit,c.discharge,k.pregnancy_start AS control_pregnancy_start
FROM cases c JOIN controls k USING(month,state,age_band,index_payer,slot)
""")
build("people", """
SELECT pair_id,1 AS pregnant,case_hvid AS hvid,idx,admit,discharge FROM pairs
UNION ALL
SELECT pair_id,0 AS pregnant,control_hvid AS hvid,idx,NULL::DATE,NULL::DATE FROM pairs
""")
assert c.execute("SELECT count(*)=count(DISTINCT hvid) FROM people").fetchone()[0]
assert c.execute("SELECT min(control_pregnancy_start-idx)>139 FROM pairs").fetchone()[0]
build("selected_dates", """
SELECT p.pair_id,p.pregnant,date_diff('day',p.idx,x.date_start) AS rel,x.date_start,
       bool_or(regexp_matches(code,'^I(10|11|12|13|15)')) AS hypertension,
       bool_or(regexp_matches(code,'^O(10|11)')) AS obstetric_hypertension,
       bool_or(regexp_matches(code,'^E(08|09|10|11|13)')) AS diabetes,
       bool_or(regexp_matches(code,'^O24(0|1|3|8)')) AS obstetric_diabetes,
       bool_or(code='D573') AS trait
FROM a.predelivery_dx x JOIN people p ON p.hvid=x.hvid
 AND x.date_start BETWEEN p.idx-449 AND coalesce(p.discharge+90,p.idx+139)
WHERE regexp_matches(code,'^(I(10|11|12|13|15)|O(10|11)|E(08|09|10|11|13)|O24(0|1|3|8)|D573$)')
GROUP BY ALL
""")
# The dedicated predelivery extract includes E10/E11/E13 and O24 codes but does not
# include E08 or E09. Its source code list is a property of this cached release.
firsts = {
    "Hypertension": ("hypertension","hypertension OR obstetric_hypertension"),
    "Diabetes": ("diabetes","diabetes OR obstetric_diabetes"),
    "Sickle cell trait": ("trait","trait"),
}
result = dict(birth_pool=pool, eligible_cases=case_count, eligible_unique_controls=control_count,
              pairs=pair_count, conditions={})
result["matching"] = c.execute("""SELECT cast(month AS varchar),count(*) FROM pairs GROUP BY 1 ORDER BY 1""").fetchall()
result["payer"] = c.execute("""SELECT index_payer,count(*) FROM pairs GROUP BY 1 ORDER BY 1""").fetchall()
result["coverage_followup"] = c.execute("""
SELECT count(*) FROM people p WHERE pregnant=1 AND EXISTS (
 SELECT 1 FROM a.medical_spans s WHERE s.hvid=p.hvid AND s.span_start<=p.idx-449 AND s.span_end>=p.discharge+90
)""").fetchone()[0]

def paired_delta(pair_count, sum_difference, different_pairs):
    d = sum_difference / pair_count
    var = max(0, (different_pairs/pair_count - d*d)/(pair_count-1))
    return [d*1000, (d-1.96*var**0.5)*1000, (d+1.96*var**0.5)*1000]

for outcome,(common, inclusive) in firsts.items():
    definitions = {"common":common}
    if common!=inclusive:
        definitions["inclusive"] = inclusive
    for spec, target in definitions.items():
        name = outcome + " " + spec
        c.execute(f"""
        CREATE OR REPLACE TEMP TABLE first_event AS
        WITH flags AS (
            SELECT pair_id,pregnant,
                   min(rel) FILTER (WHERE rel>=-84 AND ({target})) AS first_rel,
                   bool_or(rel < -84 AND ({inclusive})) AS prior_dx
            FROM selected_dates GROUP BY pair_id,pregnant
        ), eligible AS (
            SELECT p.*,f.first_rel,coalesce(f.prior_dx,false) AS prior_dx
            FROM people p LEFT JOIN flags f USING(pair_id,pregnant)
        ), eligible_pairs AS (
            SELECT pair_id FROM eligible GROUP BY pair_id HAVING NOT bool_or(prior_dx)
        )
        SELECT e.* FROM eligible e JOIN eligible_pairs USING(pair_id)
        """)
        n_eligible = c.execute("SELECT count(*)/2 FROM first_event").fetchone()[0]
        summary = dict(pairs_washout=int(n_eligible))
        for hi in [-1,83,139]:
            lo = -84 if hi == -1 else 0
            entry = -84 if hi == -1 else 0
            row=c.execute(f"""
              WITH paired AS (
                SELECT pair_id,
                  max((first_rel BETWEEN {lo} AND {hi})::INT) FILTER (WHERE pregnant=1) AS pregnant_dx,
                  max((first_rel BETWEEN {lo} AND {hi})::INT) FILTER (WHERE pregnant=0) AS control_dx
                FROM first_event
                GROUP BY pair_id HAVING NOT coalesce(bool_or(first_rel<{entry}),false)
              ), non_null AS (
                SELECT coalesce(pregnant_dx,0) AS p,coalesce(control_dx,0) AS k FROM paired
              )
              SELECT count(*),sum(p),sum(k),sum(p<>k) FROM non_null
            """).fetchone()
            n,p,k,discordant=row
            summary[str(hi)]=dict(pairs=n,pregnant=p,control=k,
                                  rd_per_1000=paired_delta(n,p-k,discordant))
        summary["weeks"] = c.execute("""
          WITH weeks AS (SELECT range AS week FROM range(-12,20))
          SELECT pregnant,week,sum(greatest(0,least(7,coalesce(first_rel+1-7*week,7)))) AS risk_days,
             count(*) FILTER (first_rel BETWEEN 7*week AND 7*week+6) AS first_dx
          FROM first_event CROSS JOIN weeks GROUP BY 1,2 ORDER BY 1,2
        """).fetchall()
        summary["through_delivery"] = c.execute(f"""
          SELECT count(*) FILTER(first_rel BETWEEN 0 AND 139),
            count(*) FILTER(first_rel BETWEEN 140 AND admit-idx-1),
            count(*) FILTER(first_rel BETWEEN admit-idx AND discharge-idx)
          FROM first_event WHERE pregnant=1
        """).fetchone()
        summary["later_dated_code"] = c.execute(f"""
          WITH eligible AS (
            SELECT f.* FROM first_event f WHERE f.pregnant=1 AND f.first_rel BETWEEN 0 AND 139
            AND EXISTS(SELECT 1 FROM a.medical_spans s
                       WHERE s.hvid=f.hvid AND s.span_start<=f.idx-449 AND s.span_end>=f.discharge+90)
          )
          SELECT count(*) AS early_count,
                 count(*) FILTER(WHERE EXISTS (
                    SELECT 1 FROM selected_dates x WHERE x.pair_id=f.pair_id AND x.pregnant=1
                       AND x.date_start>f.discharge AND x.date_start<=f.discharge+90 AND ({target})
                 )) AS postpartum_repeat
          FROM eligible f
        """).fetchone()
        result["conditions"][name]=summary
        print(name, summary["pairs_washout"],summary["-1"],summary["83"],summary["139"],summary["through_delivery"],summary["later_dated_code"],flush=True)
(scratch/"ahn_results.json").write_text(json.dumps(result,indent=2), encoding="utf-8")
print("Matching", {k:v for k,v in result.items() if k!="conditions"},flush=True)
c.close()

