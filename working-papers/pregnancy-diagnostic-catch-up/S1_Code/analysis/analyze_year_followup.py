import os
from pathlib import Path
import argparse, calendar, json, math, shutil, sys
import pandas as pd

parser = argparse.ArgumentParser()
parser.add_argument('--work', type=Path, default=Path(__file__).parent)
parser.add_argument('--output', type=Path, default=Path('analysis_outputs')/'year_followup_analysis')
args = parser.parse_args()
work, out = args.work, args.output
out.mkdir(parents=True, exist_ok=True)
ahn = Path(os.environ["WH_AHN_ROOT"]).expanduser().resolve()
import duckdb
c = duckdb.connect(str(work/'ahn_work.duckdb'), config={'threads':6, 'memory_limit':'6GB'})
c.execute(f"ATTACH '{(ahn/'Aim1_Postpartum_Heat/data/aim1-Joseph.duckdb').as_posix()}' AS a (READ_ONLY)")
c.execute(f"ATTACH '{(ahn/'analysis_heat/claims.duckdb').as_posix()}' AS b (READ_ONLY)")
protocol = json.loads((work/'protocol.json').read_text())
assert c.execute('SELECT count(*) FROM pairs').fetchone()[0] == 175505
assert c.execute('SELECT count(*)=count(DISTINCT hvid) FROM people').fetchone()[0]

def save(rows, name):
    d = rows if isinstance(rows, pd.DataFrame) else pd.DataFrame(rows)
    d.to_csv(out/name, index=False, float_format='%.12g')
    return d

definitions = [('Hypertension','hypertension','hypertension OR obstetric_hypertension'),
               ('Diabetes','diabetes','diabetes OR obstetric_diabetes'),
               ('Sickle cell trait','trait','trait')]
parts = []
for label, target, broad in definitions:
    parts.append(f"""
    WITH flags AS (
      SELECT pair_id,pregnant,
             min(rel) FILTER(WHERE rel BETWEEN -84 AND 139 AND ({target})) AS first_rel,
             bool_or(rel BETWEEN -449 AND -85 AND ({broad})) AS prior
      FROM selected_dates GROUP BY 1,2
    ), observations AS (
      SELECT p.*,f.first_rel,coalesce(f.prior,false) AS prior
      FROM people p LEFT JOIN flags f USING(pair_id,pregnant)
    ), eligible_pairs AS (
      SELECT pair_id FROM observations GROUP BY 1 HAVING NOT bool_or(prior)
    )
    SELECT '{label}' AS condition,o.pair_id,o.hvid,o.idx,o.admit,o.discharge,o.first_rel,
           o.idx+o.first_rel::INT AS first_date,k.pay_type AS delivery_payer,
           d.first_delivery_signal AS delivery_date
    FROM observations o JOIN eligible_pairs USING(pair_id)
    JOIN birth_pool k ON o.pair_id=k.delivery_id AND o.hvid=k.hvid
    JOIN b.eligible_deliveries d ON o.pair_id=d.delivery_id AND o.hvid=d.hvid
         AND o.admit=d.admit AND o.discharge=d.discharge
    WHERE o.pregnant=1 AND o.first_rel BETWEEN 0 AND 139
    """)
c.execute('CREATE OR REPLACE TABLE year_early AS '+' UNION ALL '.join('('+q+')' for q in parts))
initial = dict(c.execute('SELECT condition,count(*) FROM year_early GROUP BY 1').fetchall())
assert initial == protocol['expected_initial_counts'], initial
assert c.execute('SELECT count(*) FROM (SELECT condition,hvid,count(*) n FROM year_early GROUP BY 1,2 HAVING n<>1)').fetchone()[0] == 0
assert c.execute('SELECT count(*) FROM year_early WHERE delivery_date IS NULL OR delivery_date NOT BETWEEN admit AND discharge').fetchone()[0] == 0
print('Early-first cohorts reproduced:', initial, flush=True)

c.execute("""
CREATE OR REPLACE TABLE year_windows AS
SELECT *, discharge+1 AS annual_start,
          CAST(delivery_date+INTERVAL 1 YEAR AS DATE) AS annual_end,
          greatest(CAST(delivery_date+INTERVAL 6 MONTH AS DATE)+1,discharge+1) AS late_start
FROM year_early
""")
source_min, source_max = c.execute('SELECT min(date_start),max(date_start) FROM a.predelivery_dx').fetchone()
c.execute("""
CREATE OR REPLACE TABLE year_eligibility AS
SELECT w.*, annual_start >= ? AND annual_end <= ? AS source_available,
       EXISTS(SELECT 1 FROM a.medical_spans s WHERE s.hvid=w.hvid
              AND s.span_start<=w.discharge AND s.span_end>=w.annual_end) AS full_year_enrolled
FROM year_windows w
""", [source_min, source_max])
assert c.execute('SELECT count(*) FROM year_windows WHERE NOT (annual_start<=late_start AND late_start<=annual_end)').fetchone()[0] == 0
# Calendar-month boundaries explicitly retain leap day and handle end-of-month dates.
assert c.execute("SELECT (DATE '2023-08-31'+INTERVAL 6 MONTH)::DATE+1, (DATE '2023-03-01'+INTERVAL 1 YEAR)::DATE").fetchone() == (__import__('datetime').date(2024,3,1), __import__('datetime').date(2024,3,1))

coverage = c.execute("""
SELECT date_trunc('month',date_start)::DATE AS month, min(date_start) AS first_date,
       max(date_start) AS last_date,count(DISTINCT date_start) AS distinct_days,count(*) AS condition_records
FROM a.predelivery_dx WHERE date_start BETWEEN DATE '2023-01-01' AND DATE '2024-12-31'
GROUP BY 1 ORDER BY 1
""").df()
assert len(coverage) == 24
for row in coverage.itertuples():
    assert row.distinct_days == calendar.monthrange(row.month.year,row.month.month)[1]
    assert row.first_date.day==1 and row.last_date.day==row.distinct_days
save(coverage,'source_date_coverage.csv')

# Full diagnosis source, not the selected_dates table ending at discharge+90.
c.execute("""
CREATE OR REPLACE TABLE year_records AS
SELECT DISTINCT e.condition,e.hvid,d.date_start
FROM a.predelivery_dx d JOIN year_eligibility e ON d.hvid=e.hvid
 AND d.date_start BETWEEN e.annual_start AND e.annual_end
WHERE CASE e.condition
 WHEN 'Hypertension' THEN regexp_matches(d.code,'^I(10|11|12|13|15)')
 WHEN 'Diabetes' THEN regexp_matches(d.code,'^E(10|11|13)')
 ELSE d.code='D573' END
""")
c.execute("""
CREATE OR REPLACE TABLE year_followup AS
SELECT e.*,
       EXISTS(SELECT 1 FROM year_records r WHERE r.condition=e.condition AND r.hvid=e.hvid) AS repeat_first_year,
       EXISTS(SELECT 1 FROM year_records r WHERE r.condition=e.condition AND r.hvid=e.hvid
              AND r.date_start BETWEEN e.late_start AND e.annual_end) AS repeat_months_7_12
FROM year_eligibility e
""")
assert c.execute('SELECT count(*) FROM year_followup WHERE repeat_months_7_12 AND NOT repeat_first_year').fetchone()[0] == 0
assert c.execute('SELECT count(*) FROM year_records r JOIN year_windows e USING(condition,hvid) WHERE r.date_start<=e.discharge OR r.date_start>e.annual_end').fetchone()[0] == 0
df = c.execute('SELECT * FROM year_followup').df()

def wilson(k,n):
    if not n: return None,None,None
    p=k/n; z=1.959963984540054; den=1+z*z/n
    center=(p+z*z/(2*n))/den
    half=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/den
    return p,max(0,center-half),min(1,center+half)

rows, flow, monthly = [], [], []
payers = ['COMMERCIAL','MANAGED MEDICAID']
for condition,_,_ in definitions:
    for payer in payers:
        base = df[(df.condition==condition)&(df.delivery_payer==payer)]
        available = base[base.source_available]
        eligible = available[available.full_year_enrolled]
        flow.append(dict(condition=condition,payer_at_delivery=payer,early_first_records=len(base),
                         outside_source_dates=len(base)-len(available),
                         lacks_full_year_enrollment=len(available)-len(eligible),eligible_women=len(eligible),
                         retained_percent=100*len(eligible)/len(base)))
        for window,flag in [('first_year','repeat_first_year'),('months_7_12','repeat_months_7_12')]:
            k=int(eligible[flag].sum()); n=len(eligible); p,lo,hi=wilson(k,n)
            rows.append(dict(window=window,condition=condition,payer_at_delivery=payer,
                             repeat_records=k,eligible_women=n,proportion=p,ci_low=lo,ci_high=hi,
                             percent=100*p,percent_ci_low=100*lo,percent_ci_high=100*hi))
        for month,g in base.groupby(base.delivery_date.dt.to_period('M')):
            elig=g[g.source_available&g.full_year_enrolled]
            monthly.append(dict(condition=condition,payer_at_delivery=payer,delivery_month=str(month),
                                early_first_records=len(g),eligible_women=len(elig),
                                repeat_first_year=int(elig.repeat_first_year.sum()),
                                repeat_months_7_12=int(elig.repeat_months_7_12.sum())))
summary=save(rows,'year_followup_results.csv')
save(flow,'cohort_flow.csv')
save(monthly,'delivery_month_counts.csv')
save(df.groupby(['condition','delivery_payer'],dropna=False).size().rename('early_first_records').reset_index(),'all_delivery_payers.csv')
contrasts=[]
for window in ['first_year','months_7_12']:
    for condition,_,_ in definitions:
        r=summary[(summary.window==window)&(summary.condition==condition)].set_index('payer_at_delivery')
        commercial,medicaid=r.loc['COMMERCIAL'],r.loc['MANAGED MEDICAID']
        d=medicaid.proportion-commercial.proportion
        lo=d-math.sqrt((medicaid.proportion-medicaid.ci_low)**2+(commercial.ci_high-commercial.proportion)**2)
        hi=d+math.sqrt((medicaid.ci_high-medicaid.proportion)**2+(commercial.proportion-commercial.ci_low)**2)
        contrasts.append(dict(window=window,condition=condition,medicaid_minus_commercial_pp=100*d,
                              ci_low_pp=100*lo,ci_high_pp=100*hi))
save(contrasts,'payer_differences.csv')
metadata=dict(analysis_date='2026-11-11',initial_matched_pairs=175505,initial_early_first_counts=initial,
              unique_early_first_women=int(df.hvid.nunique()),duckdb_version=duckdb.__version__,
              diagnosis_source_min_max=[str(source_min),str(source_max)],
              all_2023_2024_calendar_days_present=True,
              source_database=str(ahn/'Aim1_Postpartum_Heat/data/aim1-Joseph.duckdb'),
              delivery_signal_database=str(ahn/'analysis_heat/claims.duckdb'),
              private_working_database=str(work/'ahn_work.duckdb'),files_contain_aggregate_data_only=True,
              same_denominator_across_windows=True,delivery_hospitalization_excluded=True,
              source_completeness_note='Calendar-day availability does not establish capture of every clinical encounter.',
              document_edited=False)
(out/'analysis_metadata.json').write_text(json.dumps(metadata,indent=2),encoding='utf-8')
shutil.copy2(work/'protocol.json',out/'analysis_protocol.json')
print(summary.to_string(index=False),flush=True)
print(pd.DataFrame(flow).to_string(index=False),flush=True)
print(pd.DataFrame(contrasts).to_string(index=False),flush=True)
c.close()
