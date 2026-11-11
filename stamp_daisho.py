#!/usr/bin/env python
# stamp_daisho.py: get a Daisho variational output ready for the Daisho Run Viewer.
#
# Writes a copy of the .nc file with the run's settings stored inside it, so the viewer can group
# runs by their settings instead of by file name. Your original file is only read.
#
# Stored in the copy:
#   global attributes : the full TOML text, case, time window, run tag, and, from the job log if you
#                       give one, CG iterations, converged, final residual, solve time and job time
#   variables         : cg_iteration, cg_residual, cg_time_s (the CG history from the log, dim cg_step)
#
# Needs: python 3 with numpy and netCDF4 (conda install -c conda-forge netcdf4)
#
# One file (dry run first; nothing is written without --write):
#   python stamp_daisho.py var_20220807_time_1.nc --toml var_20220807_time_1.toml --log job_1.log
#   python stamp_daisho.py var_20220807_time_1.nc --toml var_20220807_time_1.toml --log job_1.log --write
#
# Optional labels (otherwise taken from the file):
#   --case 20220807      case name           (default: the date of time_coverage_start; set it when
#                                             two cases share a day, e.g. 20220917_1 and 20220917_2)
#   --time time_1        time window name    (default: HH:MM of time_coverage_start)
#   --tag  mu2_roi225    a short run name    (default: the TOML file name)
#   --out-dir DIR        where the copy goes (default: ./daisho_web)
#
# The log is the text Daisho printed while it ran (e.g. the Slurm .log). Without one the viewer still
# groups the run by its settings, but has no run time or convergence curve for it. If the log has
# lines starting "start: <date>" and "end: <date>  exit code: N", the job time is read from them.

import os
import re
import sys
import shutil
import argparse
from datetime import datetime

import numpy as np
import netCDF4

ANSI_RE  = re.compile(r'\x1b\[[0-9;?]*[A-Za-z]')
START_RE = re.compile(r'^start:\s+(.+?)(?:\s{2,}|\s+node:|$)')
END_RE   = re.compile(r'^end:\s+(.+?)\s+exit code:\s+(-?\d+)')
OUTER_RE = re.compile(r'outer\s+(\d+):\s+(\d+)\s+CG iterations\s+\(inner tolerance reached:\s+(true|false)\)')
CG_RE    = re.compile(r'^\s*cg\s+(\d+)\s+\S*=\s*([0-9.eE+-]+)\s+\S*=\s*([0-9.eE+-]+).*?\bt=\s*([0-9.]+)s')


def parse_time(s):
    s = ' '.join(s.split())
    s = re.sub(r'\s[A-Z]{2,5}\s(\d{4})$', r' \1', s)          # drop a time zone name (MST, UTC, ...)
    for fmt in ('%a %b %d %I:%M:%S %p %Y', '%a %b %d %H:%M:%S %Y', '%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S'):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            pass
    return None


def parse_log(path):
    out = {'start': None, 'end': None, 'exit_code': None, 'iterations': None, 'converged': None}
    its, res, ts = [], [], []
    it_off, t_off, total = 0, 0.0, 0
    with open(path, errors='replace') as f:
        for raw in f:
            for line in raw.replace('\r', '\n').split('\n'):
                line = ANSI_RE.sub('', line)
                s = line.strip()
                m = START_RE.match(s)
                if m and out['start'] is None:
                    out['start'] = parse_time(m.group(1))
                    continue
                m = CG_RE.match(line)
                if m:
                    it, t = int(m.group(1)) + it_off, float(m.group(4)) + t_off
                    if its and it == its[-1]:
                        continue
                    its.append(it)
                    res.append(float(m.group(3)))
                    ts.append(t)
                    continue
                m = OUTER_RE.search(line)
                if m:
                    total += int(m.group(2))
                    out['converged'] = m.group(3) == 'true'
                    it_off = total                         # a later outer loop restarts the CG count
                    t_off = ts[-1] if ts else t_off
                    continue
                m = END_RE.match(s)
                if m:
                    out['end'] = parse_time(m.group(1))
                    out['exit_code'] = int(m.group(2))
    out['iterations'] = total or (its[-1] if its else None)
    out['cg'] = (np.array(its, 'i4'), np.array(res, 'f8'), np.array(ts, 'f8'))
    out['final_resid'] = res[-1] if res else None
    out['solve_s'] = ts[-1] if ts else None
    out['wall_s'] = (out['end'] - out['start']).total_seconds() if out['start'] and out['end'] else None
    return out


def main():
    ap = argparse.ArgumentParser(description='Store a Daisho run\'s settings inside a copy of its output, for the Daisho Run Viewer.')
    ap.add_argument('nc', help='the Daisho output .nc file')
    ap.add_argument('--toml', required=True, help='the TOML the run used')
    ap.add_argument('--log', help='the text Daisho printed while it ran (optional)')
    ap.add_argument('--case', help='case name (default: date of time_coverage_start)')
    ap.add_argument('--time', help='time window name (default: HH:MM of time_coverage_start)')
    ap.add_argument('--tag', help='short run name (default: the TOML file name)')
    ap.add_argument('--out-dir', default='daisho_web', help='folder for the stamped copy (default: ./daisho_web)')
    ap.add_argument('--write', action='store_true', help='write the copy (default: dry run)')
    ap.add_argument('--overwrite', action='store_true', help='replace a stamped copy that already exists')
    a = ap.parse_args()

    for p in [a.nc, a.toml] + ([a.log] if a.log else []):
        if not os.path.isfile(p):
            sys.exit(f'not found: {p}')
    try:
        with netCDF4.Dataset(a.nc) as d:
            start = str(getattr(d, 'time_coverage_start', ''))
            missing = [v for v in ('DBZ', 'W', 'QFLAG', 'x', 'y', 'z') if v not in d.variables]
    except OSError as err:
        sys.exit(f'could not open {a.nc} as netCDF ({err}). The first argument is the Daisho output .nc file.')
    if missing:
        sys.exit(f'{a.nc} has no {", ".join(missing)}: is it a Daisho variational output?')
    case = a.case or (start[:10].replace('-', '') if start else 'unknown')
    time = a.time or (start[11:16] if len(start) >= 16 else os.path.splitext(os.path.basename(a.nc))[0])
    tag = a.tag or os.path.splitext(os.path.basename(a.toml))[0]
    toml_text = open(a.toml).read()
    L = parse_log(a.log) if a.log else None
    dest = os.path.join(a.out_dir, os.path.basename(a.nc))

    print(f"{'DRY RUN' if not a.write else 'WRITING'}")
    print(f"  output : {a.nc}")
    print(f"  toml   : {a.toml} ({len(toml_text)} characters)")
    print(f"  case   : {case}    time window: {time}    run tag: {tag}")
    if L:
        it = L['iterations']
        conv = {True: 'converged', False: 'not converged'}.get(L['converged'], 'convergence unknown')
        job = f"job time {L['wall_s'] / 60:.0f} min" if L['wall_s'] else 'no start/end lines, so no job time'
        print(f"  log    : {a.log}")
        print(f"           {it if it is not None else 'no'} CG iterations, {conv}, {len(L['cg'][0])} residual points, {job}")
    else:
        print("  log    : none (no run time or convergence curve in the viewer)")
    print(f"  copy   : {dest}")
    if os.path.abspath(dest) == os.path.abspath(a.nc):
        sys.exit('the copy would replace the original; choose another --out-dir')
    if os.path.exists(dest) and not a.overwrite:
        print('  a stamped copy already exists; left alone (use --overwrite to replace it)')
        return
    if not a.write:
        print('\nnothing written. Run again with --write to make the copy.')
        return

    os.makedirs(a.out_dir, exist_ok=True)
    tmp = dest + '.partial'
    shutil.copy2(a.nc, tmp)
    num = lambda v: -1.0 if v is None else float(v)
    with netCDF4.Dataset(tmp, 'a') as d:
        attrs = {
            'daisho_web_stamp_version': 1,
            'daisho_toml': toml_text,
            'daisho_case': case,
            'daisho_time_window': time,
            'daisho_run_tag': tag,
            'daisho_source_nc': os.path.abspath(a.nc),
            'daisho_source_toml': os.path.abspath(a.toml),
            'daisho_stamped_at': datetime.now().replace(microsecond=0).isoformat(sep=' '),
        }
        if L:
            attrs.update({
                'daisho_source_log': os.path.abspath(a.log),
                'daisho_job_start_local': L['start'].isoformat(sep=' ') if L['start'] else '',
                'daisho_job_end_local': L['end'].isoformat(sep=' ') if L['end'] else '',
                'daisho_job_wall_seconds': num(L['wall_s']),
                'daisho_solve_seconds': num(L['solve_s']),
                'daisho_cg_iterations': int(L['iterations'] if L['iterations'] is not None else -1),
                'daisho_final_residual': num(L['final_resid']),
            })
            if L['converged'] is not None:
                attrs['daisho_converged'] = int(L['converged'])
        for k, v in attrs.items():
            d.setncattr(k, v)
        it, res, ts = L['cg'] if L else ([], [], [])
        if len(it):
            if 'cg_step' in d.dimensions:
                sys.exit(f'{a.nc} already has a cg_step dimension; is it already stamped?')
            d.createDimension('cg_step', len(it))
            for name, data, typ, long in [('cg_iteration', it, 'i4', 'CG iteration (counted across outer loops)'),
                                          ('cg_residual', res, 'f8', 'relative CG residual ||r||/||r0||'),
                                          ('cg_time_s', ts, 'f8', 'CG solve time since the start of the solve')]:
                v = d.createVariable(name, typ, ('cg_step',))
                v.long_name = long
                if name == 'cg_time_s':
                    v.units = 's'
                v[:] = data
    os.replace(tmp, dest)
    with netCDF4.Dataset(dest) as d:
        ok = d.getncattr('daisho_case') == case and len(d.getncattr('daisho_toml')) == len(toml_text)
    print(f"\n{'ok' if ok else 'CHECK'}: {dest} ({os.path.getsize(dest) / 1e6:.0f} MB)")


if __name__ == '__main__':
    main()
