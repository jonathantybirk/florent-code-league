# Installation

Source: https://game.code.florent.vc/docs/cli-installation

The `fcode` CLI is the primary tool for working with Florent Code League. It handles authentication, local match running, replay viewing, and bot submission.

## Requirements

- Python 3.12 or 3.13. Python 3.14 is not supported. Check your version:

```
python --version
```

- pip, which is bundled with all standard Python distributions.

## Install

```
pip install fcode
```

Verify the installation:

```
fcode --version
```

## Virtual environments

It is good practice to install `fcode` inside a virtual environment:

```
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install fcode
```

## Authenticate

Link the CLI to your platform account:

```
fcode login
```

A browser window opens where you approve the connection. Once authorised, your credentials are stored locally and remain valid until you explicitly log out.

```
fcode logout
```

## Updating

```
pip install --upgrade fcode
```

It is recommended to update before each competition to ensure you have the latest engine version.
