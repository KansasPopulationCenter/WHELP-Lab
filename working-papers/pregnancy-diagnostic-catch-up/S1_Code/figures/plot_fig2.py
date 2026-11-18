"""Create publication Fig 2 from the previously verified aggregate payer rates."""
from pathlib import Path
import json
import os

OUT = Path(os.environ['PLOS_FIGURE_OUTPUT'])
OUT.mkdir(parents=True,exist_ok=True)
SOURCE = Path(os.environ['PLOS_DATA_ROOT']) / 'payer'
os.environ.setdefault("MPLCONFIGDIR", str(OUT / "matplotlib_cache"))
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
import numpy as np
import pandas as pd
from PIL import Image

font_path = font_manager.findfont("Arial", fallback_to_default=False)
plt.rcParams.update({
    "font.family": "Arial", "font.size": 9,
    "axes.titlesize": 9, "axes.labelsize": 9,
    "xtick.labelsize": 8, "ytick.labelsize": 8,
    "legend.fontsize": 8.5,
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.linewidth": 0.6, "xtick.major.width": 0.6,
    "ytick.major.width": 0.6, "xtick.major.size": 3,
    "ytick.major.size": 3, "axes.axisbelow": True,
    "savefig.facecolor": "white", "figure.facecolor": "white",
})
contact = pd.read_csv(SOURCE / "outpatient_contact_timing.csv")
diagnoses = pd.read_csv(SOURCE / "diagnosis_timing.csv")
payers = [("COMMERCIAL", "Commercial", "#0072B2"),
          ("MANAGED MEDICAID", "Managed Medicaid", "#D55E00")]
roles = [("case", "entering pregnancy", "-", "o"),
         ("control", "comparison", "--", "s")]
panels = [("Outpatient evaluation days", "A  Outpatient evaluation days"),
          ("Hypertension", "B  Chronic hypertension"),
          ("Diabetes", "C  Non-gestational diabetes"),
          ("Sickle cell trait", "D  Sickle cell trait")]
expected_starts = np.arange(-12, 20, 4)
fig, axes = plt.subplots(2, 2, figsize=(7.5, 6.3))
fig.subplots_adjust(left=0.105, right=0.985, bottom=0.095,
                    top=0.845, wspace=0.34, hspace=0.36)
audited_series = []
for ax, (metric, title) in zip(axes.flat, panels):
    for payer, payer_name, color in payers:
        for role, role_name, linestyle, marker in roles:
            if metric == "Outpatient evaluation days":
                frame = contact[(contact.payer == payer) &
                                (contact.pregnant == int(role == "case"))].sort_values("start_week")
                rates = frame.evaluation_days_per_100_woman_weeks.to_numpy()
                recomputed = frame.evaluation_days.to_numpy() / (frame.n_women.to_numpy() * 4) * 100
                ylabel = "Evaluation days per 100\nwoman-weeks"
            else:
                frame = diagnoses[(diagnoses.payer == payer) &
                                  (diagnoses.role == role) &
                                  (diagnoses.outcome == metric)].sort_values("start_week")
                rates = frame.rate_per_1000_woman_weeks.to_numpy()
                recomputed = frame.first_records.to_numpy() / (frame.person_days.to_numpy() / 7) * 1000
                ylabel = "First records per 1,000\nwoman-weeks at risk"
            starts = frame.start_week.to_numpy()
            assert np.array_equal(starts, expected_starts), (metric, payer, role)
            assert np.isfinite(rates).all() and (rates >= 0).all()
            assert np.allclose(rates, recomputed, rtol=1e-10, atol=1e-10)
            label = f"{payer_name}, {role_name}"
            line, = ax.plot(starts + 2, rates, color=color, linestyle=linestyle,
                           marker=marker, linewidth=1.25, markersize=3.2,
                           markeredgewidth=0.55, label=label, zorder=3)
            assert np.array_equal(line.get_ydata(), rates)
            audited_series.append({"panel": metric, "payer": payer, "role": role,
                                   "label": label, "color": color,
                                   "linestyle": linestyle, "marker": marker,
                                   "weeks": (starts + 2).tolist(), "rates": rates.tolist()})
    ax.axvspan(0, 20, color="#F0F2F4", linewidth=0, zorder=0)
    ax.axvline(0, color="#777777", linewidth=0.65, zorder=2)
    ax.set_title(title, loc="left", fontweight="bold", pad=8)
    ax.set_xlim(-12, 20)
    ax.set_ylim(bottom=0)
    ax.set_xticks(np.arange(-12, 21, 4))
    ax.set_ylabel(ylabel, labelpad=5)
    ax.grid(axis="y", color="#D8D8D8", linewidth=0.5, zorder=1)
for ax in axes[1]:
    ax.set_xlabel("Weeks from the shared index date", labelpad=6)
handles, labels = axes[0, 0].get_legend_handles_labels()
expected_labels = [f"{name}, {role_name}"
                   for _, name, _ in payers for _, role_name, _, _ in roles]
assert labels == expected_labels
legend = fig.legend(handles, labels, loc="upper center", bbox_to_anchor=(0.54, 0.985),
                    ncol=2, frameon=False, handlelength=2.2, handletextpad=0.65,
                    columnspacing=2.1, labelspacing=0.65, borderaxespad=0)
fig.canvas.draw()
renderer = fig.canvas.get_renderer()
figure_box = fig.bbox
for artist in [legend] + [item for ax in axes.flat for item in
                         [ax._left_title, ax.xaxis.label, ax.yaxis.label] +
                         ax.get_xticklabels() + ax.get_yticklabels()]:
    if not artist.get_visible():
        continue
    if hasattr(artist, "get_text") and not artist.get_text():
        continue
    box = artist.get_window_extent(renderer)
    assert figure_box.x0 <= box.x0 and box.x1 <= figure_box.x1
    assert figure_box.y0 <= box.y0 and box.y1 <= figure_box.y1
png = OUT / "Fig2.png"
tif = OUT / "Fig2.tif"
fig.savefig(png, dpi=600)
plt.close(fig)
with Image.open(png) as original:
    assert original.size == (4500, 3780)
    rgb = original.convert("RGB")
    rgb.save(tif, compression="tiff_lzw", dpi=(600, 600))
with Image.open(tif) as output:
    assert output.mode == "RGB" and output.size == (4500, 3780)
    assert output.info["compression"] == "tiff_lzw"
    assert tuple(output.info["dpi"]) == (600, 600)
assert tif.stat().st_size < 10_000_000
report = {"source": str(SOURCE), "font_path": font_path,
          "dimensions_inches": [7.5, 6.3], "dimensions_pixels": [4500, 3780],
          "dpi": 600, "tiff_mode": "RGB", "tiff_compression": "tiff_lzw",
          "tiff_bytes": tif.stat().st_size, "png_bytes": png.stat().st_size,
          "rate_and_series_audit": "passed", "series": audited_series}
(OUT / "Fig2_audit.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps({key: value for key, value in report.items() if key != "series"}, indent=2))

