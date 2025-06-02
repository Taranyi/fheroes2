# Python Support Guide

This project includes helper tools written in Python. If you want to extend these tools or create new ones, set up a dedicated Python environment.

## Prerequisites

* Python 3.8 or higher
* `pip` package manager

## Setting up a virtual environment

When running the build system a `venv` directory will be created automatically if it does not exist and the required packages from `requirements.txt` will be installed. Any stale `venv` directory without a proper interpreter is removed automatically before a new environment is created. You only need to perform the following steps manually if you want to work with the Python tools outside of the build process.

1. Create a virtual environment in the project directory:

   ```bash
   python3 -m venv venv
   ```

2. Activate the environment:

   * **Linux/macOS**
     ```bash
     source venv/bin/activate
     ```
   * **Windows**
     ```cmd
     venv\Scripts\activate
     ```

3. Install the required packages:

   ```bash
   pip install -r requirements.txt
   ```

## Running the tools

After activating the virtual environment you can run any script from `script/tools`:

```bash
python script/tools/changelog_update_metainfo.py --help
```

## Troubleshooting

* If a command reports that Python is missing, verify that Python 3.8 or newer is installed and available in your `PATH`.
* When a script fails because a module cannot be imported, reinstall the dependencies:

  ```bash
  pip install --force-reinstall -r requirements.txt
  ```
* As a last resort, delete the `venv` directory and set up the environment again.

