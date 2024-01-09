# Package for Building Python Extensions to Spotfire® 

This package provides functions used for integrating Python with Spotfire, including: 
* reading and writing files in Spotfire Binary Data Format (SBDF)
* building Spotfire Packages (SPKs) for distributing Python interpreters and custom packages with Spotfire
* internal handler code for executing Data Functions from Spotfire

### Installation
```sh
pip install spotfire
```

Additionally, [extras](https://peps.python.org/pep-0508/#extras) may be specified (as `spotfire[extra]` instead of
simply `spotfire`) to include the required Python packages to support optional functionality:

| Extra                       | Functionality                                |
|-----------------------------|----------------------------------------------|
| `spotfire[geo]`             | Geographic data processing                   |
| `spotfire[plot]`            | Plotting support with all supported packages |
| `spotfire[plot-matplotlib]` | Plotting support using just `matplotlib`     |
| `spotfire[plot-pil]`        | Plotting support using just `Pillow`         |
| `spotfire[plot-seaborn]`    | Plotting support using just `seaborn`        |
| `spotfire[dev,lint]`        | Internal development                         |

### License
BSD-type 3-Clause License.  See the file ```LICENSE``` included in the package.