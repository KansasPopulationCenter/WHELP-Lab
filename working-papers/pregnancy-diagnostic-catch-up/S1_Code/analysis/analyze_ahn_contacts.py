import os

from pathlib import Path
import json, sys, time
import numpy as np
import pandas as pd

scratch = Path(sys.argv[1])
ahn = Path(os.environ["WH_AHN_ROOT"]).expanduser().resolve()
import duckdb

c = duckdb.connect(str(scratch / "ahn_work.duckdb"), config={"threads":10,"memory_limit":"8GB"})
c.execute("SET preserve_insertion_order=false")
c.execute("SET temp_directory=?", [str(scratch / "spill_ahn")])
procedures = (ahn / "data" / "procedure.csv").as_posix()
office = [str(k) for lo,hi in [(99201,99205),(99211,99215),(99241,99245),(99381,99387),
                                (99391,99397),(99441,99443)] for k in range(lo,hi+1)]+["G0463","T1015"]
prenatal = ["0500F","0501F","0502F"]
hemo = ["83020","83021"]
def quote(codes):
    return ", ".join(repr(code) for code in codes)
started = time.monotonic()
print("Scanning WH_Ahn procedure records",flush=True)
c.execute(f"""
CREATE OR REPLACE TABLE procedure_days AS
WITH hits AS (
    SELECT hvid,try_cast(date_start AS DATE) AS svc,procedure_code,
           location_of_care_code,location_of_care_qual
    FROM read_csv('{procedures}',delim='|',header=true,all_varchar=true,strict_mode=true,parallel=true)
    WHERE procedure_code IN ({quote(office+prenatal+hemo)})
      AND date_start >= '2021-01-01' AND date_start <= '2024-01-01'
      AND hvid IN (SELECT hvid FROM people)
)
SELECT p.pair_id,p.pregnant, date_diff('day',p.idx,h.svc) AS rel,
       bool_or(procedure_code IN ({quote(office)})
           AND NOT (coalesce(location_of_care_qual,'')='POS' AND
                    coalesce(location_of_care_code,'') IN ('20','21','23'))) AS em,
       bool_or(procedure_code IN ({quote(prenatal)})) AS prenatal,
       bool_or(procedure_code IN ({quote(hemo)})) AS hemo
FROM hits h JOIN people p ON h.hvid=p.hvid AND h.svc BETWEEN p.idx-449 AND p.idx+139
GROUP BY ALL
""")
print("Procedure days",c.execute("SELECT count(*), count(*) FILTER(em),count(*) FILTER(prenatal),count(*) FILTER(hemo) FROM procedure_days").fetchall(),round(time.monotonic()-started,1),"seconds",flush=True)
c.execute("""
CREATE OR REPLACE TABLE encounter_counts AS
SELECT p.pair_id,p.pregnant,
       count(*) FILTER (d.rel BETWEEN -449 AND -85 AND d.em) AS prior_em,
       count(*) FILTER (d.rel BETWEEN -84 AND -1 AND d.em) AS before_em,
       count(*) FILTER (d.rel BETWEEN 0 AND 83 AND d.em) AS early_em,
       count(*) FILTER (d.rel BETWEEN 0 AND 139 AND d.em) AS through20_em,
       count(*) FILTER (d.rel BETWEEN 0 AND 83 AND d.prenatal) AS early_prenatal,
       count(*) FILTER (d.rel BETWEEN 0 AND 139 AND d.hemo) AS through20_hemo
FROM people p LEFT JOIN procedure_days d USING(pair_id,pregnant)
GROUP BY p.pair_id,p.pregnant
""")
summary={}
summary["contact"]=c.execute("""
SELECT pregnant,count(*),sum(prior_em),count(*) FILTER(prior_em=0),
       sum(before_em),sum(early_em),sum(through20_em),sum(early_prenatal),sum(through20_hemo),
       count(*) FILTER(through20_hemo>0) FROM encounter_counts GROUP BY pregnant ORDER BY 1
""").fetchall()
summary["weeks"]=c.execute("""
SELECT pregnant,floor(rel/7)::INT AS week,count(*) FILTER(em),count(*) FILTER(prenatal),count(*) FILTER(hemo)
FROM procedure_days WHERE rel BETWEEN -84 AND 139 GROUP BY 1,2 ORDER BY 1,2
""").fetchall()
contact_pair=c.execute("""
    SELECT
     k.before_em AS before_control, p.before_em AS before_case, k.early_em AS early_control, p.early_em AS early_case
    FROM encounter_counts p JOIN encounter_counts k USING(pair_id)
    WHERE p.pregnant=1 AND k.pregnant=0
""").df()
diff_change=(contact_pair.early_case-contact_pair.before_case-contact_pair.early_control+contact_pair.before_control)
avg=float(diff_change.mean())
se=float(diff_change.std(ddof=1)/np.sqrt(len(diff_change)))
summary["difference_in_change"]=[avg,avg-1.96*se,avg+1.96*se]
summary["conditions"]={}
conditions={"Hypertension":("hypertension","hypertension OR obstetric_hypertension"),
            "Diabetes":("diabetes","diabetes OR obstetric_diabetes"),"Sickle cell trait":("trait","trait")}
for label,(code,broad) in conditions.items():
    c.execute(f"""
CREATE OR REPLACE TEMP TABLE eligible AS
WITH dx AS (
  SELECT pair_id,pregnant,min(rel) FILTER(WHERE rel BETWEEN -84 AND 139 AND ({code})) AS first_rel,
       bool_or(rel BETWEEN -449 AND -85 AND ({broad})) AS prior_dx
  FROM selected_dates GROUP BY 1,2
), people AS (
  SELECT e.*,d.first_rel,coalesce(d.prior_dx,false) AS prior_dx
  FROM encounter_counts e LEFT JOIN dx d USING(pair_id,pregnant)
), pairs AS (
  SELECT pair_id FROM people GROUP BY pair_id HAVING NOT bool_or(prior_dx)
)
SELECT p.* FROM people p JOIN pairs USING(pair_id)
""")
    contact_yield=c.execute("""
    SELECT q.pregnant,
      count(*) FILTER(d.em AND d.rel BETWEEN -84 AND -1) AS before_contact,
      count(*) FILTER(d.em AND d.rel BETWEEN 0 AND 83) AS early_contact,
      count(*) FILTER(d.em AND d.rel=q.first_rel AND d.rel BETWEEN -84 AND -1) AS before_code_contact,
      count(*) FILTER(d.em AND d.rel=q.first_rel AND d.rel BETWEEN 0 AND 83) AS early_code_contact,
      count(*) FILTER(d.prenatal AND d.rel=q.first_rel AND d.rel BETWEEN 0 AND 83) AS early_code_prenatal
    FROM eligible q LEFT JOIN procedure_days d
       ON q.pair_id=d.pair_id AND q.pregnant=d.pregnant AND d.rel BETWEEN -84 AND least(83,coalesce(first_rel,83))
    GROUP BY 1 ORDER BY 1
    """).fetchall()
    by_prior=c.execute("""
    WITH paired AS (
      SELECT p.pair_id,
           coalesce(p.first_rel BETWEEN 0 AND 139,false)::INT AS case_dx,
           coalesce(k.first_rel BETWEEN 0 AND 139,false)::INT AS control_dx,
           CASE WHEN p.prior_em=0 AND k.prior_em=0 THEN 'none in either'
                WHEN p.prior_em>0 AND k.prior_em>0 THEN 'some in both' ELSE 'discordant' END AS prior
      FROM eligible p JOIN eligible k USING(pair_id)
      WHERE p.pregnant=1 AND k.pregnant=0 AND coalesce(p.first_rel,0)>=0 AND coalesce(k.first_rel,0)>=0
    )
    SELECT prior,count(*),sum(case_dx),sum(control_dx),sum(case_dx<>control_dx)
    FROM paired GROUP BY 1 ORDER BY 1
    """).fetchall()
    by_prior=[[*x, (x[2]-x[3])/x[1]*1000,
               np.sqrt((x[4]/x[1]-((x[2]-x[3])/x[1])**2)/(x[1]-1))*1000] for x in by_prior]
    has_hemo=c.execute("""
      SELECT pregnant,count(*),count(*) FILTER(WHERE EXISTS (
        SELECT 1 FROM procedure_days p WHERE p.pair_id=q.pair_id AND p.pregnant=q.pregnant
         AND p.hemo AND p.rel BETWEEN first_rel-30 AND first_rel
      ))
      FROM eligible q WHERE first_rel BETWEEN 0 AND 139 GROUP BY 1 ORDER BY 1
    """).fetchall()
    summary["conditions"][label]=dict(yield_by_role=contact_yield,prior=by_prior,hemo_before=has_hemo)
(scratch/"ahn_procedures.json").write_text(json.dumps(summary,indent=2),encoding="utf-8")
print(json.dumps({k:v for k,v in summary.items() if k!="weeks"},indent=2),flush=True)
c.close()

