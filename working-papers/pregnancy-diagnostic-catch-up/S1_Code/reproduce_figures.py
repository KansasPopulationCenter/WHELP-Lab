"""Reproduce all three figures using only the accompanying aggregate data."""
from pathlib import Path
import argparse, os, subprocess, sys

parser=argparse.ArgumentParser()
parser.add_argument('--data',type=Path,default=Path(__file__).resolve().parent.parent/'S1_Data')
parser.add_argument('--output',type=Path,default=Path('reproduced_figures'))
args=parser.parse_args()
assert (args.data/'primary'/'ahn_results.json').is_file(), 'Extract the accompanying S1_Data archive first.'
args.output.mkdir(parents=True,exist_ok=True)
env=os.environ.copy()
env['PLOS_DATA_ROOT']=str(args.data.resolve())
env['PLOS_FIGURE_OUTPUT']=str(args.output.resolve())
for number in [1,2,3]:
    subprocess.run([sys.executable,str(Path(__file__).resolve().parent/'figures'/f'plot_fig{number}.py')],env=env,check=True)
print('Completed: three PNGs, three 600-dpi RGB LZW TIFFs, and aggregate validation reports.')
