# Daisho Run Viewer

A website for looking at [Daisho.jl](https://github.com/mmbell/Daisho.jl) variational outputs and comparing runs.

Drop a folder of Daisho `.nc` outputs on the page. The viewer groups them into cases, runs and time windows using the settings stored inside each file (not the file names), then shows:

- **Runs**: every run and time window in a table
- **3D view**: W, reflectivity and QFLAG in 3D, stepping through time, with a movie export
- **Slices**: plan views with N–S and E–W cross sections, clicked anywhere on the plan view
- **Map**: every case on one map
- **Compare runs**: run cost, convergence, wind coverage, W by height and the storm through time

Your files never leave your computer. They are read inside your browser.

## Getting your files ready

The viewer reads the run's settings from inside each output. Run `stamp_daisho.py` (also on the Home page of the site) to copy your Daisho TOML, and the timing and convergence from the log, into a copy of each output. Unstamped files still load, but every run shows as "No settings stored".

## Running it

The site is a single page, `index.html`, plus the `map` folder of coast, state and county outlines. Serve the folder from any web server (GitHub Pages works). Opening `index.html` straight from your disk works too, except for the map outlines.

Plotting uses [Plotly](https://plotly.com/javascript/), file reading uses [h5wasm](https://github.com/usnistgov/h5wasm), map projections use [proj4js](https://github.com/proj4js/proj4js), and movies use [mp4-muxer](https://github.com/Vanilagy/mp4-muxer). Map outlines are from [world-atlas](https://github.com/topojson/world-atlas) and [us-atlas](https://github.com/topojson/us-atlas) (Natural Earth and US Census data).
