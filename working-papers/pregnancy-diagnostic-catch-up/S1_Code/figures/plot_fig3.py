"""Combine the verified first-year and restricted beyond-year follow-up figures."""
from pathlib import Path
import argparse
import csv
import math
import os
import json

parser = argparse.ArgumentParser()
parser.add_argument('--first-year', type=Path, default=Path(os.environ['PLOS_DATA_ROOT'])/'followup'/'first_year.csv')
parser.add_argument('--beyond-year', type=Path, default=Path(os.environ['PLOS_DATA_ROOT'])/'followup'/'beyond_first_year_min90.csv')
parser.add_argument('--output', type=Path, default=Path(os.environ['PLOS_FIGURE_OUTPUT']))
args = parser.parse_args()
ROOT = args.output
ROOT.mkdir(parents=True,exist_ok=True)
os.environ['MPLCONFIGDIR'] = str(ROOT/'mpl_cache')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from PIL import Image

panels = []
for source,window in [(args.first_year,'first_year'),(args.beyond_year,'beyond_first_year')]:
    with source.open(newline='',encoding='utf-8-sig') as f:
        rows = [r for r in csv.DictReader(f) if r['window'] == window
                and r.get('analysis','primary') == 'primary']
    assert len(rows) == 6
    data = {(r['condition'],r['payer_at_delivery']):r for r in rows}
    assert len(data) == 6
    panels.append(data)
conditions = ['Hypertension','Diabetes','Sickle cell trait']
payers = ['COMMERCIAL','MANAGED MEDICAID']
colors = ['#0072B2','#D55E00']
names = ['Commercial','Managed Medicaid']
markers = ['o','s']
expected_counts = [
    [(147,388),(388,933),(62,183),(156,417),(10,81),(88,419)],
    [(84,273),(144,553),(41,132),(67,255),(3,54),(36,247)],
]
z = 1.959963984540054
for data,expected in zip(panels,expected_counts):
    k = 0
    for condition in conditions:
        for payer in payers:
            r = data[(condition,payer)]
            count,total = int(r['repeat_records']),int(r['eligible_women'])
            assert (count,total) == expected[k]
            k += 1
            p = count/total
            den = 1+z*z/total
            center = (p+z*z/(2*total))/den
            half = z*math.sqrt(p*(1-p)/total+z*z/(4*total*total))/den
            assert abs(100*p-float(r['percent'])) < 1e-6
            assert abs(100*(center-half)-float(r['percent_ci_low'])) < 1e-6
            assert abs(100*(center+half)-float(r['percent_ci_high'])) < 1e-6
            assert float(r['percent_ci_high']) <= 50
for key,r in panels[1].items():
    assert 90 < float(r['followup_min_days']) <= float(r['followup_median_days']) <= float(r['followup_max_days'])
    assert int(r['eligible_women']) != int(panels[0][key]['eligible_women'])
min_days = min(int(float(r['followup_min_days'])) for r in panels[1].values())
max_days = max(int(float(r['followup_max_days'])) for r in panels[1].values())

plt.rcParams.update({
    'font.family':'Arial','font.size':10,'axes.labelsize':10,
    'xtick.labelsize':9,'ytick.labelsize':10,
    'axes.spines.top':False,'axes.spines.right':False,
    'axes.spines.left':False,'axes.linewidth':.7,'pdf.fonttype':42,
})
fig,axes = plt.subplots(2,1,figsize=(7.5,7.0))
fig.subplots_adjust(left=.255,right=.79,bottom=.10,top=.86,hspace=.50)
titles = ['A  Any repeat diagnosis during the first year after delivery',
          'B  Any repeat diagnosis more than one year after discharge']
for ax,data,title in zip(axes,panels,titles):
    for center,condition in zip([2,1,0],conditions):
        for i,payer in enumerate(payers):
            r = data[(condition,payer)]
            y = center+(.14 if i == 0 else -.14)
            val,lo,hi = [float(r[k]) for k in ['percent','percent_ci_low','percent_ci_high']]
            ax.errorbar(val,y,xerr=[[val-lo],[hi-val]],fmt=markers[i],color=colors[i],
                        markersize=5.5,linewidth=1.5,capsize=3,capthick=1.2,
                        markeredgewidth=.75,zorder=3)
            ax.text(1.055,y,f"{int(r['repeat_records']):,} / {int(r['eligible_women']):,}",
                    transform=ax.get_yaxis_transform(),va='center',ha='left',
                    fontsize=10,color=colors[i],clip_on=False)
    ax.set_yticks([2,1,0],['Chronic hypertension','Non-gestational\ndiabetes','Sickle cell trait'])
    ax.tick_params(axis='y',length=0,pad=10)
    ax.set_ylim(-.45,2.48)
    ax.set_xlim(0,50)
    ax.set_xticks(range(0,51,10))
    ax.grid(axis='x',color='#e1e1e1',linewidth=.65,zorder=0)
    ax.set_axisbelow(True)
    ax.set_title(title,fontsize=11,fontweight='bold',loc='left',pad=29)
    ax.text(1.055,2.46,'Women with code /\neligible women',
            transform=ax.get_yaxis_transform(),va='bottom',ha='left',
            fontsize=9,color='#303030',clip_on=False)
axes[-1].set_xlabel('Women with at least one repeat diagnosis (%)',labelpad=9)
handles = [Line2D([0],[0],color=colors[i],marker=markers[i],linewidth=1.5,
                  markersize=5.5,label=names[i]) for i in range(2)]
fig.legend(handles=handles,loc='upper center',bbox_to_anchor=(.54,.99),
           ncol=2,frameon=False,fontsize=10,handlelength=2,columnspacing=2.5)
footer = (
    'Bars show Wilson 95% confidence intervals. Payer was measured at delivery.\n'
    'First condition records occurred before 20 weeks of pregnancy. Eligible samples differ between panels.\n'
    'A: From the day after discharge through the first delivery anniversary; continuous medical enrollment\n'
    '    was required from discharge through that anniversary.\n'
    'B: From the day after the first discharge anniversary through 31 December 2024; >90 days of available\n'
    f'    follow-up were required. Eligible periods ranged from {min_days} to {max_days} days and remained unequal.\n'
    '    Medical enrollment was continuous from discharge through 31 December 2024.'
)
# Caption content is retained in audit and supplied to the manuscript.
png = ROOT/'Fig3.png'
tif = ROOT/'Fig3.tif'
fig.savefig(png,dpi=600,facecolor='white')
plt.close(fig)
with Image.open(png) as im:
    assert im.size == (4500,4200)
    assert all(abs(v-600)<.01 for v in im.info['dpi'])
    im.convert('RGB').save(tif,compression='tiff_lzw',dpi=(600,600))
with Image.open(tif) as im:
    assert im.size == (4500,4200)
    assert im.mode == 'RGB'
    assert im.info['dpi'] == (600,600)
assert tif.stat().st_size < 10_000_000
audit = {'source_A':str(args.first_year.resolve()),'source_B':str(args.beyond_year.resolve()),
         'rows_A':list(panels[0].values()),'rows_B':list(panels[1].values()),
         'exact_prior_counts_preserved':True,'percentages_and_wilson_intervals_verified':True,
         'different_panel_denominators_verified':True,
         'B_followup_min_days':min_days,'B_followup_max_days':max_days,
         'B_more_than_90_days_available_followup_required_and_verified':True,
         'footer':footer,'width_inches':7.5,'height_inches':7.0,
         'pixel_width':4500,'pixel_height':4200,'dpi':600,'mode':'RGB',
         'compression':'LZW','tiff_bytes':tif.stat().st_size,
         'png':str(png),'tif':str(tif)}
(ROOT/'Fig3_audit.json').write_text(json.dumps(audit,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in audit.items() if not k.startswith('rows_')}))

