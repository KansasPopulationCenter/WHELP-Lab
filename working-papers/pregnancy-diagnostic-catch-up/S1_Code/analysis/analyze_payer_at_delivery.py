"""Exploratory payer-at-delivery heterogeneity in the existing matched cohort.

Input: the original diagnostic analysis's ahn_work.duckdb (read only).
Output: aggregate tables only; no patient identifiers leave the working database.
Primary strata use the pregnancy-group woman's medical enrollment payer at her
delivery discharge. Original matched controls are retained. Sensitivities use
concordant own-delivery payer and the original matching-payer classification.
"""
from pathlib import Path
import argparse
import json
import math
import sys
import numpy as np
import pandas as pd

parser = argparse.ArgumentParser()
parser.add_argument('--work', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--duckdb-deps', type=Path)
args = parser.parse_args()
if args.duckdb_deps:
    sys.path.insert(0, str(args.duckdb_deps))
import duckdb

out = args.output
out.mkdir(parents=True, exist_ok=True)
c = duckdb.connect(':memory:')
c.execute('SET threads=6')
c.execute('SET memory_limit=\'6GB\'')
c.execute(f"ATTACH '{(args.work/'ahn_work.duckdb').as_posix()}' AS d (READ_ONLY)")
c.execute("""CREATE TEMP VIEW payer_pairs AS
SELECT p.*, b.pay_type AS case_delivery_payer, k.pay_type AS control_delivery_payer
FROM d.pairs p JOIN d.birth_pool b ON p.case_hvid=b.hvid
JOIN d.birth_pool k ON p.control_hvid=k.hvid
""")
pairs = c.execute('SELECT * FROM payer_pairs').df()
assert len(pairs) == 175505 and pairs.pair_id.is_unique
assert pd.concat([pairs.case_hvid,pairs.control_hvid]).is_unique

COMM = 'COMMERCIAL'
MED = 'MANAGED MEDICAID'
PAYERS = [COMM, MED]
SETS = ['case_delivery_payer', 'same_own_delivery_payer', 'index_matching_payer']

def subset(df, analysis, payer):
    if analysis == 'case_delivery_payer':
        return df[df.case_delivery_payer == payer]
    if analysis == 'same_own_delivery_payer':
        return df[(df.case_delivery_payer == payer) & (df.control_delivery_payer == payer)]
    if analysis == 'index_matching_payer':
        return df[df.index_payer == payer]
    raise ValueError(analysis)

def estimate(values, scale=1.0):
    x = np.asarray(values, dtype=float)
    n = len(x)
    assert n >= 2 and np.isfinite(x).all(), 'Invalid subgroup for variance estimation'
    value = float(x.mean()) * scale
    se = float(x.std(ddof=1) / np.sqrt(n)) * scale
    p = math.erfc(abs(value / se) / np.sqrt(2)) if se else (1.0 if value == 0 else 0.0)
    return dict(n_pairs=n, estimate=value, se=se, ci_low=value-1.96*se,
                ci_high=value+1.96*se, p_value=p)

def interaction(commercial, medicaid):
    value = medicaid['estimate'] - commercial['estimate']
    se = np.sqrt(medicaid['se']**2 + commercial['se']**2)
    p = math.erfc(abs(value / se) / np.sqrt(2)) if se else (1.0 if value == 0 else 0.0)
    return dict(medicaid_minus_commercial=value, se=se,
                ci_low=value-1.96*se, ci_high=value+1.96*se, p_value=p)

def save(rows, name):
    df = rows if isinstance(rows,pd.DataFrame) else pd.DataFrame(rows)
    df.to_csv(out/name,index=False,float_format='%.12g')
    return df

save(pairs.groupby(['index_payer','case_delivery_payer'],dropna=False).size().reset_index(name='n_pairs'),
     'index_to_delivery_payer.csv')
save(pairs.groupby(['case_delivery_payer','control_delivery_payer'],dropna=False).size().reset_index(name='n_pairs'),
     'delivery_payer_concordance.csv')
save([{'analysis':a,'payer':p,'n_pairs':len(subset(pairs,a,p))} for a in SETS for p in PAYERS],
     'analysis_sample_sizes.csv')

contact = c.execute("""SELECT q.*,
 p.prior_em AS case_prior, p.before_em AS case_before, p.early_em AS case_after,
 k.prior_em AS control_prior, k.before_em AS control_before, k.early_em AS control_after
FROM payer_pairs q JOIN d.encounter_counts p ON q.pair_id=p.pair_id AND p.pregnant=1
JOIN d.encounter_counts k ON q.pair_id=k.pair_id AND k.pregnant=0
""").df()
assert len(contact) == len(pairs) and contact.pair_id.is_unique
contact['pair_difference_in_changes'] = ((contact.case_after-contact.case_before)-
                                        (contact.control_after-contact.control_before))
original_contact = json.loads((args.work/'ahn_procedures.json').read_text())['difference_in_change']
pooled_contact = estimate(contact.pair_difference_in_changes)
assert np.allclose([pooled_contact['estimate'],pooled_contact['ci_low'],pooled_contact['ci_high']],
                   original_contact, rtol=0,atol=1e-12)
contact_rows, interactions, baseline_rows = [], [], []
for analysis in SETS:
    estimates = {}
    for payer in PAYERS:
        g = subset(contact,analysis,payer)
        e = estimate(g.pair_difference_in_changes)
        estimates[payer] = e
        row = dict(analysis=analysis,payer=payer,**e)
        for role in ['case','control']:
            for period in ['prior','before','after']:
                row[f'{role}_{period}_mean_days'] = float(g[f'{role}_{period}'].mean())
            row[f'{role}_prior_zero_pct'] = float((g[f'{role}_prior']==0).mean()*100)
            row[f'{role}_before_zero_pct'] = float((g[f'{role}_before']==0).mean()*100)
            row[f'{role}_change_mean_days'] = float((g[f'{role}_after']-g[f'{role}_before']).mean())
        contact_rows.append(row)
    interactions.append(dict(analysis=analysis,outcome='Outpatient evaluation days',definition='contact',
        window='12-week difference in changes',units='days per woman',**interaction(estimates[COMM],estimates[MED])))
    for variable in ['case_prior','case_before']:
        es = {p:estimate(subset(contact,analysis,p)[variable]) for p in PAYERS}
        baseline_rows.append(dict(analysis=analysis,measure=variable,**interaction(es[COMM],es[MED])))
save(contact_rows,'outpatient_contact.csv')
save(baseline_rows,'baseline_contact_differences.csv')

original = json.loads((args.work/'ahn_results.json').read_text())
condition_rows, timing_rows, yield_rows, test_rows = [], [], [], []
definitions = [
 ('Hypertension','common','hypertension','hypertension OR obstetric_hypertension'),
 ('Hypertension','inclusive','hypertension OR obstetric_hypertension','hypertension OR obstetric_hypertension'),
 ('Diabetes','common','diabetes','diabetes OR obstetric_diabetes'),
 ('Diabetes','inclusive','diabetes OR obstetric_diabetes','diabetes OR obstetric_diabetes'),
 ('Sickle cell trait','common','trait','trait'),
]
windows = [('Before index',-84,-1),('First 12 weeks',0,83),('Before 20 weeks',0,139)]
for outcome,definition,target,broad in definitions:
    c.execute(f"""CREATE OR REPLACE TEMP TABLE eligible_first AS
    WITH flags AS (
      SELECT pair_id,pregnant,
       min(rel) FILTER(WHERE rel>=-84 AND ({target})) AS first_rel,
       bool_or(rel BETWEEN -449 AND -85 AND ({broad})) AS prior
      FROM d.selected_dates GROUP BY 1,2
    ), all_people AS (
      SELECT p.pair_id,p.pregnant,f.first_rel,coalesce(f.prior,false) AS prior
      FROM d.people p LEFT JOIN flags f USING(pair_id,pregnant)
    ) SELECT * FROM all_people
      QUALIFY NOT bool_or(prior) OVER (PARTITION BY pair_id)
    """)
    dx = c.execute("""SELECT q.*,
        p.first_rel AS case_first, k.first_rel AS control_first
        FROM payer_pairs q JOIN eligible_first p ON q.pair_id=p.pair_id AND p.pregnant=1
        JOIN eligible_first k ON q.pair_id=k.pair_id AND k.pregnant=0""").df()
    for window,lo,hi in windows:
        risk = dx if lo<0 else dx[(dx.case_first.fillna(0)>=0)&(dx.control_first.fillna(0)>=0)]
        risk = risk.copy()
        risk['case_event'] = risk.case_first.between(lo,hi).fillna(False).astype(int)
        risk['control_event'] = risk.control_first.between(lo,hi).fillna(False).astype(int)
        ref = original['conditions'][f'{outcome} {definition}'][str(hi)]
        assert len(risk)==ref['pairs']
        assert int(risk.case_event.sum())==ref['pregnant']
        assert int(risk.control_event.sum())==ref['control']
        pooled = estimate(risk.case_event-risk.control_event,1000)
        assert np.allclose([pooled['estimate'],pooled['ci_low'],pooled['ci_high']],ref['rd_per_1000'],atol=1e-12,rtol=0)
        for analysis in SETS:
            estimates = {}
            for payer in PAYERS:
                g = subset(risk,analysis,payer)
                e = estimate(g.case_event-g.control_event,1000)
                estimates[payer] = e
                condition_rows.append(dict(analysis=analysis,payer=payer,outcome=outcome,definition=definition,
                    window=window,case_events=int(g.case_event.sum()),control_events=int(g.control_event.sum()),
                    case_per_1000=float(g.case_event.mean()*1000),control_per_1000=float(g.control_event.mean()*1000),**e))
            interactions.append(dict(analysis=analysis,outcome=outcome,definition=definition,window=window,
                units='first records per 1,000 women',**interaction(estimates[COMM],estimates[MED])))
    if definition != 'common':
        continue
    for payer in PAYERS:
        g = subset(dx,'case_delivery_payer',payer)
        for role in ['case','control']:
            event = g[f'{role}_first'].astype('float64').to_numpy(na_value=np.nan)
            for lo in range(-84,140,28):
                hi = lo+27
                events = int(((event>=lo)&(event<=hi)).sum())
                days = float(np.maximum(0,np.minimum(hi,np.nan_to_num(event,nan=hi))+1-lo).sum())
                timing_rows.append(dict(payer=payer,role=role,outcome=outcome,start_week=lo/7,
                    end_week=(hi+1)/7,first_records=events,person_days=days,
                    rate_per_1000_woman_weeks=events/(days/7)*1000 if days else None))
    # Contact yield and testing are descriptive; each woman's observation ends
    # on her own first record, irrespective of the partner's pre-index event.
    y=c.execute("""SELECT q.case_delivery_payer AS payer,e.pregnant,
       CASE WHEN p.rel<0 THEN 'Before index' ELSE 'First 12 weeks' END AS window,
       count(*) AS evaluation_days,
       count(*) FILTER(p.rel=e.first_rel) AS first_records
       FROM eligible_first e JOIN payer_pairs q USING(pair_id)
       JOIN d.procedure_days p ON p.pair_id=e.pair_id AND p.pregnant=e.pregnant
        AND p.em AND p.rel BETWEEN -84 AND least(83,coalesce(e.first_rel,83))
       WHERE q.case_delivery_payer IN ('COMMERCIAL','MANAGED MEDICAID')
       GROUP BY 1,2,3""").df()
    y['outcome']=outcome
    y['first_records_per_1000_evaluation_days']=y.first_records/y.evaluation_days*1000
    yield_rows.extend(y.to_dict('records'))
    if outcome=='Sickle cell trait':
        t=c.execute("""SELECT q.case_delivery_payer AS payer,count(*) AS first_trait_records,
          count(*) FILTER(WHERE EXISTS(SELECT 1 FROM d.procedure_days p
           WHERE p.pair_id=e.pair_id AND p.pregnant=e.pregnant AND p.hemo
            AND p.rel BETWEEN e.first_rel-30 AND e.first_rel)) AS recent_tests
          FROM eligible_first e JOIN payer_pairs q USING(pair_id)
          WHERE e.pregnant=1 AND e.first_rel BETWEEN 0 AND 139
            AND q.case_delivery_payer IN ('COMMERCIAL','MANAGED MEDICAID') GROUP BY 1""").df()
        t['recent_test_pct']=t.recent_tests/t.first_trait_records*100
        test_rows=t.to_dict('records')

save(condition_rows,'diagnosis_risk_differences.csv')
save(timing_rows,'diagnosis_timing.csv')
save(yield_rows,'diagnosis_per_evaluation_day.csv')
save(test_rows,'trait_testing.csv')
interactions_df=pd.DataFrame(interactions)
# Four prespecified-for-this-run heterogeneity contrasts: outpatient change and
# each of the three shared-code conditions by 20 weeks. Holm is supplementary;
# confidence intervals remain pointwise and all analyses remain exploratory.
primary_mask=(interactions_df.analysis=='case_delivery_payer') & (
    (interactions_df.definition=='contact') |
    ((interactions_df.definition=='common')&(interactions_df.window=='Before 20 weeks')))
primary_indices=interactions_df.index[primary_mask].tolist()
assert len(primary_indices)==4
ordered=sorted(primary_indices,key=lambda i:interactions_df.at[i,'p_value'])
running=0.0
interactions_df['holm_p_four_primary_tests']=np.nan
for rank,i in enumerate(ordered):
    running=max(running,min(1.0,(4-rank)*interactions_df.at[i,'p_value']))
    interactions_df.at[i,'holm_p_four_primary_tests']=running
save(interactions_df,'payer_heterogeneity_tests.csv')

ct=c.execute("""SELECT q.case_delivery_payer AS payer,p.pregnant,
    floor(p.rel/28)*4 AS start_week,count(*) AS evaluation_days
    FROM d.procedure_days p JOIN payer_pairs q USING(pair_id)
    WHERE p.em AND p.rel BETWEEN -84 AND 139
      AND q.case_delivery_payer IN ('COMMERCIAL','MANAGED MEDICAID')
    GROUP BY 1,2,3""").df()
ns={p:len(subset(pairs,'case_delivery_payer',p)) for p in PAYERS}
ct['n_women']=ct.payer.map(ns)
ct['evaluation_days_per_100_woman_weeks']=ct.evaluation_days/(ct.n_women*4)*100
save(ct,'outpatient_contact_timing.csv')

metadata={
 'analysis_date':'2026-11-10','original_matched_pairs':len(pairs),
 'primary_payer_definition':'Medical enrollment payer at the pregnancy-group woman\'s delivery discharge; original matched control retained.',
 'medicaid_scope':'MANAGED MEDICAID only; cohort continuously medically enrolled from 449 days before index through delivery discharge for pregnancy-group women.',
 'payer_source':'delivery_covariates.pay_type, carried into birth_pool.pay_type. One medical enrollment payer active on discharge; overlapping types are MULTIPLE; no match is NOT ENROLLED AT DISCHARGE.',
 'unsupported_primary_delivery_payer_pairs':int((~pairs.case_delivery_payer.isin(PAYERS)).sum()),
 'payer_sensitivities':SETS[1:],
 'inference':'Empirical variance of within-pair contrasts; independent pairs. Medicaid-minus-commercial standard error is sqrt(SE_M^2+SE_C^2). Normal 95% pointwise intervals and two-sided tests. Four primary heterogeneity tests also have supplementary Holm-adjusted p-values.',
 'primary_heterogeneity_family':['12-week outpatient difference in changes','20-week chronic hypertension shared-code risk difference','20-week non-gestational diabetes shared-code risk difference','20-week sickle cell trait risk difference'],
 'diagnosis_windows':{'Before index':[-84,-1],'First 12 weeks':[0,83],'Before 20 weeks':[0,139]},
 'history_window':[-449,-85],
 'interpretation':'Exploratory effect heterogeneity in recorded contact/documentation, not causal effects of payer. Delivery payer is measured after pregnancy starts. Contact is billed evaluation days, not all care. Absolute diagnosis differences can reflect population composition and underlying condition prevalence.',
 'validation':'Rebuilt original n, events, risk differences and confidence intervals exactly for all 15 condition-definition/window combinations; pooled contact change also reproduced within 1e-12. No patient reuse across pairs.',
 'duckdb_version':duckdb.__version__,
}
(out/'analysis_metadata.json').write_text(json.dumps(metadata,indent=2),encoding='utf-8')
print(json.dumps(metadata,indent=2))
print('PRIMARY CONTACT',json.dumps([r for r in contact_rows if r['analysis']=='case_delivery_payer']))
print('PRIMARY INTERACTIONS',interactions_df[primary_mask].to_json(orient='records'))
c.close()
