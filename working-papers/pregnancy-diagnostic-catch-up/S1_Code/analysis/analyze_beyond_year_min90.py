import os
from pathlib import Path
import argparse, json, math, shutil, sys
import pandas as pd

parser=argparse.ArgumentParser()
parser.add_argument('--work',type=Path,default=Path(__file__).parent)
parser.add_argument('--output',type=Path,default=Path('analysis_outputs')/'beyond_year_min90_analysis')
args=parser.parse_args()
work,out=args.work,args.output
out.mkdir(parents=True,exist_ok=True)
ahn = Path(os.environ["WH_AHN_ROOT"]).expanduser().resolve()
import duckdb
c=duckdb.connect(str(work/'ahn_work.duckdb'),config={'threads':6,'memory_limit':'6GB'})
c.execute(f"ATTACH '{(ahn/'Aim1_Postpartum_Heat/data/aim1-Joseph.duckdb').as_posix()}' AS a (READ_ONLY)")
protocol=json.loads((work/'beyond_protocol.json').read_text())
minimum_followup_days=protocol['minimum_followup_days']
assert minimum_followup_days==91
assert c.execute('SELECT count(*) FROM pairs').fetchone()[0]==175505
initial=dict(c.execute('SELECT condition,count(*) FROM year_early GROUP BY 1').fetchall())
assert initial==protocol['initial_counts']
source_min,source_max=c.execute('SELECT min(date_start),max(date_start) FROM a.predelivery_dx').fetchone()
assert str(source_max)=='2024-12-31'

def save(data,name):
    d=data if isinstance(data,pd.DataFrame) else pd.DataFrame(data)
    d.to_csv(out/name,index=False,float_format='%.12g')
    return d

# Recompute window and enrollment instead of relying on feasibility flags.
c.execute("""
CREATE OR REPLACE TABLE beyond_eligibility AS
WITH windows AS (
 SELECT *, (discharge+INTERVAL 1 YEAR)::DATE+1 AS window_start,
           DATE '2024-12-31' AS window_end
 FROM year_early
)
SELECT w.*, window_start<=window_end AS source_available,
       window_end-window_start+1 AS observation_days,
       EXISTS(SELECT 1 FROM a.medical_spans s WHERE s.hvid=w.hvid
              AND s.span_start<=w.discharge AND s.span_end>=w.window_end) AS covered_continuously
FROM windows w
""")
assert c.execute('SELECT count(*) FROM beyond_eligibility WHERE window_start<discharge OR (source_available AND observation_days<1)').fetchone()[0]==0
c.execute("""
CREATE OR REPLACE TABLE beyond_records AS
SELECT DISTINCT e.condition,e.hvid,d.date_start
FROM a.predelivery_dx d JOIN beyond_eligibility e ON d.hvid=e.hvid
 AND d.date_start BETWEEN e.window_start AND e.window_end
WHERE CASE e.condition
 WHEN 'Hypertension' THEN regexp_matches(d.code,'^I(10|11|12|13|15)')
 WHEN 'Diabetes' THEN regexp_matches(d.code,'^E(10|11|13)')
 ELSE d.code='D573' END
""")
c.execute("""
CREATE OR REPLACE TABLE beyond_followup AS
SELECT e.*, EXISTS(SELECT 1 FROM beyond_records r WHERE r.condition=e.condition AND r.hvid=e.hvid) AS repeat_record
FROM beyond_eligibility e
""")
assert c.execute('SELECT count(*) FROM beyond_records r JOIN beyond_eligibility e USING(condition,hvid) WHERE r.date_start<e.window_start OR r.date_start>e.window_end').fetchone()[0]==0
assert c.execute('SELECT count(*) FROM (SELECT condition,hvid,count(*) n FROM beyond_followup GROUP BY 1,2 HAVING n<>1)').fetchone()[0]==0
df=c.execute('SELECT * FROM beyond_followup').df()

def wilson(k,n):
    p=k/n;z=1.959963984540054;den=1+z*z/n
    center=(p+z*z/(2*n))/den
    half=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/den
    return p,max(0,center-half),min(1,center+half)

conditions=['Hypertension','Diabetes','Sickle cell trait']
payers=['COMMERCIAL','MANAGED MEDICAID']
rows,flow,monthly,comparisons=[],[],[],[]
previous=pd.read_csv(Path(__file__).resolve().parents[1]/'reference_data'/'beyond_year_unrestricted.csv').set_index(['condition','payer_at_delivery'])
for condition in conditions:
    for payer in payers:
        base=df[(df.condition==condition)&(df.delivery_payer==payer)]
        available=base[base.source_available]
        long_enough=available[available.observation_days>=minimum_followup_days]
        elig=long_enough[long_enough.covered_continuously]
        assert (elig.observation_days>90).all()
        unrestricted=available[available.covered_continuously]
        old=previous.loc[(condition,payer)]
        assert len(unrestricted)==int(old.eligible_women)
        assert int(unrestricted.repeat_record.sum())==int(old.repeat_records)
        k=int(elig.repeat_record.sum());n=len(elig);p,lo,hi=wilson(k,n)
        comparisons.append(dict(condition=condition,payer_at_delivery=payer,
                                previous_repeat_records=int(old.repeat_records),previous_eligible_women=int(old.eligible_women),
                                previous_percent=float(old.percent),restricted_repeat_records=k,
                                restricted_eligible_women=n,restricted_percent=100*p,
                                excluded_previous_eligible_women=len(unrestricted)-n,
                                excluded_previous_repeat_records=int(unrestricted.repeat_record.sum())-k))
        rows.append(dict(window='beyond_first_year',condition=condition,payer_at_delivery=payer,
                         repeat_records=k,eligible_women=n,proportion=p,ci_low=lo,ci_high=hi,
                         percent=100*p,percent_ci_low=100*lo,percent_ci_high=100*hi,
                         followup_min_days=int(elig.observation_days.min()),
                         followup_p25_days=float(elig.observation_days.quantile(.25)),
                         followup_median_days=float(elig.observation_days.median()),
                         followup_p75_days=float(elig.observation_days.quantile(.75)),
                         followup_max_days=int(elig.observation_days.max()),
                         total_observation_days=int(elig.observation_days.sum())))
        flow.append(dict(condition=condition,payer_at_delivery=payer,early_first_records=len(base),
                         no_followup_after_first_anniversary=len(base)-len(available),
                         only_1_to_90_days_available=len(available)-len(long_enough),
                         lacks_continuous_enrollment_to_source_end=len(long_enough)-n,
                         eligible_women=n,retained_percent=100*n/len(base)))
        for month,g in base.groupby(base.discharge.dt.to_period('M')):
            e=g[g.source_available&g.covered_continuously&(g.observation_days>=minimum_followup_days)]
            monthly.append(dict(condition=condition,payer_at_delivery=payer,discharge_month=str(month),
                                early_first_records=len(g),eligible_women=len(e),
                                repeat_records=int(e.repeat_record.sum()),
                                observation_days=int(e.observation_days.sum())))
summary=save(rows,'beyond_year_results.csv')
save(flow,'cohort_flow.csv')
save(comparisons,'comparison_with_unrestricted.csv')
save(monthly,'discharge_month_counts.csv')
save(df.groupby(['condition','delivery_payer'],dropna=False).size().rename('early_first_records').reset_index(),'all_delivery_payers.csv')
contrasts=[]
for condition in conditions:
    r=summary[summary.condition==condition].set_index('payer_at_delivery')
    commercial,medicaid=r.loc['COMMERCIAL'],r.loc['MANAGED MEDICAID']
    d=medicaid.proportion-commercial.proportion
    lo=d-math.sqrt((medicaid.proportion-medicaid.ci_low)**2+(commercial.ci_high-commercial.proportion)**2)
    hi=d+math.sqrt((medicaid.ci_high-medicaid.proportion)**2+(commercial.proportion-commercial.ci_low)**2)
    contrasts.append(dict(condition=condition,medicaid_minus_commercial_pp=100*d,ci_low_pp=100*lo,ci_high_pp=100*hi,
                          interpretation='Descriptive; follow-up duration differs across women and payer groups'))
save(contrasts,'payer_differences.csv')
metadata=dict(analysis_date='2026-11-11',initial_matched_pairs=175505,initial_early_first_counts=initial,
              unique_early_first_women=int(df.hvid.nunique()),duckdb_version=duckdb.__version__,
              diagnosis_source_min_max=[str(source_min),str(source_max)],
              source_database=str(ahn/'Aim1_Postpartum_Heat/data/aim1-Joseph.duckdb'),
              private_working_database=str(work/'ahn_work.duckdb'),files_contain_aggregate_data_only=True,
              followup_length_varies=True,eligible_followup_min_days=int(summary.followup_min_days.min()),
              eligible_followup_max_days=int(summary.followup_max_days.max()),
              continuous_medical_enrollment='Discharge through 2024-12-31',
              followup_anchor='First calendar anniversary of discharge, not the delivery-date proxy',
              user_confirmed_repeat_diagnosis_and_variable_window=True,document_edited=False)
metadata['minimum_followup_days']=minimum_followup_days
metadata['threshold_description']='More than 90 available days after the first discharge anniversary'
metadata['unrestricted_results_reproduced_before_applying_threshold']=True
(out/'analysis_metadata.json').write_text(json.dumps(metadata,indent=2),encoding='utf-8')
shutil.copy2(work/'beyond_protocol.json',out/'analysis_protocol.json')
print(summary.to_string(index=False),flush=True)
print(pd.DataFrame(flow).to_string(index=False),flush=True)
print(pd.DataFrame(contrasts).to_string(index=False),flush=True)
c.close()
