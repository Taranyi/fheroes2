# Python Support Guide

This project includes helper tools written in Python. If you want to extend these tools or create new ones, set up a dedicated Python environment.

## Prerequisites

* Python 3.8 or higher
* `pip` package manager

## Setting up a virtual environment

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

