# sleeper_log
A terminal-themed Sleeper Fantasy Football League HTML report generator.

## Dependencies
From the repository root, run the following to create a Python virtual environment and install the dependencies.
```Shell
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```
**NOTE:** Enter `deactivate` to exit the virtual environment.

## Usage

The script generates an HTML report (`sleeper_log.html`) for your Sleeper fantasy football league. You can provide league information in several ways:

### Method 1: Sleeper Username (Interactive Selection)
```Shell
# Search by username and select from available leagues
python3 sleeper_log.py --username <username>

# Narrow down by specific year
python3 sleeper_log.py --username <username> --year <year>
```

### Method 2: League ID (Direct)
```Shell
# Using command-line argument
python3 sleeper_log.py --league-id <league id>

# Or using environment variable
export LEAGUE_ID=123456789012345678
python3 sleeper_log.py
```

### Command-line Options
```
--league-id, -l
    League ID (overrides LEAGUE_ID environment variable)
--username, -u
    Sleeper username used to search for leagues
--year, -y
    Season year to narrow down league choices (used with --username)
--help, -h
    Show help message
```

## AI Credit
The following models aided in the development of this project:  
`Claude Sonnet 4` `GPT-5`
