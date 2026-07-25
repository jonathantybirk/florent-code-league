# Installation

Source: https://game.code.florent.vc/docs/cli-installation

## Overview

The `fcode` CLI is the primary tool for working with Florent Code League. It manages authentication, local match execution, replay viewing, and bot submission.

## Requirements

Users need Python 3.12 or 3.13 installed—notably, **Python 3.14 is not supported**. The pip package manager, which comes standard with Python distributions, is also required. Version can be checked via `python --version`.

## Installation Steps

Installation occurs through pip:

```
pip install fcode
```

Users should verify successful setup by running `fcode --version`.

### Virtual Environments

Best practices recommend installing within a virtual environment using these commands:

```
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install fcode
```

## Authentication

Users link their CLI to their account via `fcode login`, which opens a browser for authorization. Credentials then store locally and remain active until explicitly removed with `fcode logout`.

## Updates

The tool updates through:

```
pip install --upgrade fcode
```

Updating before each competition ensures access to the latest engine version.
