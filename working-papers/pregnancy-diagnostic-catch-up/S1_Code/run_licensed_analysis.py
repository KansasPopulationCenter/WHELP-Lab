"""Run original licensed-input analyses in their required order; never publishes raw outputs."""
from pathlib import Path
import argparse, os, shutil, subprocess, sys

parser=argparse.ArgumentParser()
parser.add_argument('--source-root',type=Path,required=True,help='Local WH_Ahn prepared-input directory; see INPUTS.txt.')
parser.add_argument('--work',type=Path,required=True,help='Private working directory: will contain patient-level intermediate databases.')
parser.add_argument('--output',type=Path,required=True,help='Local aggregate-output directory.')
args=parser.parse_args()
root=Path(__file__).resolve().parent
for relative in ['Aim1_Postpartum_Heat/data/aim1-Joseph.duckdb','analysis_heat/claims.duckdb','data/procedure.csv']:
    assert (args.source_root/relative).is_file(), f'Missing required prepared input: {relative}'
args.work.mkdir(parents=True,exist_ok=True);args.output.mkdir(parents=True,exist_ok=True)
env=os.environ.copy();env['WH_AHN_ROOT']=str(args.source_root.resolve())
def run(name,*arguments):
    subprocess.run([sys.executable,str(root/'analysis'/name),*map(str,arguments)],env=env,check=True)
run('analyze_ahn.py',args.work.resolve())
run('analyze_ahn_contacts.py',args.work.resolve())
run('analyze_payer_at_delivery.py','--work',args.work.resolve(),'--output',args.output.resolve()/'payer_at_delivery_analysis')
shutil.copy2(root/'protocols'/'year_followup.json',args.work/'protocol.json')
run('analyze_year_followup.py','--work',args.work.resolve(),'--output',args.output.resolve()/'year_followup_analysis')
shutil.copy2(root/'protocols'/'beyond_year_min90.json',args.work/'beyond_protocol.json')
run('analyze_beyond_year_min90.py','--work',args.work.resolve(),'--output',args.output.resolve()/'beyond_year_min90_analysis')
print('Analyses completed locally. Working databases contain private patient-level records and must not be distributed.')
