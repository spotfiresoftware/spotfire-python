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
| `spotfire[polars]`          | Polars DataFrame support                     |
| `spotfire[dev,lint]`        | Internal development                         |

Once installed, `export_data()` accepts `polars.DataFrame` and `polars.Series` directly, and
`import_data()` can return a `polars.DataFrame`:

```python
import spotfire.sbdf as sbdf

df = sbdf.import_data("data.sbdf", output_format=sbdf.OutputFormat.POLARS)
```

> **Note for Spotfire data functions:** Spotfire's bundled Python interpreter does not include
> Polars. To use Polars inside a data function, configure Spotfire to use a custom Python
> environment that has `polars` installed. Polars is a large binary package (~44 MB), so
> Spotfire Packages (SPKs) that bundle it will be significantly larger than typical packages.

### License
BSD-type 3-Clause License.  See the file ```LICENSE``` included in the package.