"""Re-render current Figure 1 from its original verified primary-cohort aggregates."""
from pathlib import Path
import json, os, hashlib
ROOT=Path(os.environ['PLOS_FIGURE_OUTPUT'])
ROOT.mkdir(parents=True,exist_ok=True)
SOURCE=Path(os.environ['PLOS_DATA_ROOT'])/'primary'
os.environ['MPLCONFIGDIR']=str(ROOT/'matplotlib_cache')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from PIL import Image

ahn=json.loads((SOURCE/'ahn_results.json').read_text(encoding='utf-8'))
procedures=json.loads((SOURCE/'ahn_procedures.json').read_text(encoding='utf-8'))
n_pairs=ahn['pairs']
assert n_pairs==175505
def phase_rates(role,rows,count,denominator):
    out=[]
    for week in range(-12,20,4):
        sub=[r for r in rows if r[0]==role and week<=r[1]<week+4]
        assert len(sub)==4
        out.append(sum(r[count] for r in sub)*1000/denominator(sub))
    return out

font_path=font_manager.findfont('Arial',fallback_to_default=False)
plt.rcParams.update({'font.family':'Arial','font.size':9,'axes.labelsize':8.7,
    'axes.titlesize':10,'xtick.labelsize':8.4,'ytick.labelsize':8.4,
    'pdf.fonttype':42,'axes.spines.top':False,'axes.spines.right':False,
    'axes.edgecolor':'#65717a','axes.labelcolor':'#25313b'})
fig,axes=plt.subplots(2,2,figsize=(7.5,5.0))
fig.subplots_adjust(left=.11,right=.982,top=.85,bottom=.13,wspace=.38,hspace=.50)
weeks=list(range(-10,20,4))
series=[
    ('A  Outpatient evaluation days','Days per 100 woman-weeks',procedures['weeks'],2,lambda _:n_pairs*40),
    ('B  First hypertension code','First codes per 1,000 at-risk weeks',ahn['conditions']['Hypertension common']['weeks'],3,lambda sub:sum(r[2] for r in sub)/7),
    ('C  First diabetes code','First codes per 1,000 at-risk weeks',ahn['conditions']['Diabetes common']['weeks'],3,lambda sub:sum(r[2] for r in sub)/7),
    ('D  First sickle cell trait code','First codes per 1,000 at-risk weeks',ahn['conditions']['Sickle cell trait common']['weeks'],3,lambda sub:sum(r[2] for r in sub)/7)]
audit=[]
for ax,(title,ylabel,rows,count,denominator) in zip(axes.flat,series):
    ax.set_title(title,loc='left',fontweight='bold',color='#172431',pad=7)
    ax.axvspan(0,20,color='#ecf2f5',zorder=0)
    ax.axvline(0,linewidth=.75,color='#70808b',zorder=1)
    for role,color,linestyle,marker,label in [(1,'#1c536b','-','o','Entering pregnancy'),(0,'#9a4a16','--','s','Comparison women')]:
        rates=phase_rates(role,rows,count,denominator)
        line,=ax.plot(weeks,rates,color=color,ls=linestyle,marker=marker,linewidth=1.55,markersize=3.4,label=label,zorder=3)
        assert list(line.get_ydata())==rates
        audit.append({'panel':title,'role':role,'weeks':weeks,'rates':rates,'color':color,'linestyle':linestyle,'marker':marker})
    ax.set_xlim(-12,20)
    ax.set_ylim(bottom=0)
    ax.set_xticks([-12,-8,-4,0,4,8,12,16,20])
    ax.set_ylabel(ylabel)
    ax.grid(axis='y',color='#dce1e4',linewidth=.5)
for ax in axes[-1]:
    ax.set_xlabel('Weeks from the matched index date')
handles,labels=axes[0,0].get_legend_handles_labels()
fig.legend(handles,labels,loc='upper center',bbox_to_anchor=(.5,.976),ncol=2,frameon=False,handlelength=2.7)
fig.savefig(ROOT/'Fig1.png',dpi=600,facecolor='white')
plt.close(fig)
with Image.open(ROOT/'Fig1.png') as im:
    assert im.size==(4500,3000)
    im.convert('RGB').save(ROOT/'Fig1.tif',compression='tiff_lzw',dpi=(600,600))
report={'figure':1,'font_path':font_path,'font_range_pt':[8.4,10],
    'source_files':[str(SOURCE/'ahn_results.json'),str(SOURCE/'ahn_procedures.json')],
    'source_sha256':{name:hashlib.sha256((SOURCE/name).read_bytes()).hexdigest() for name in ['ahn_results.json','ahn_procedures.json']},
    'primary_pairs':n_pairs,'series':audit,
    'dimensions_inches':[7.5,5.0],'dpi':600,'dimensions_pixels':[4500,3000]}
(ROOT/'Fig1_audit.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in report.items() if k!='series'}))
