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

## Running `sleeper_log.py`
A league ID is is required for `sleeper_log` to generate a report. Provide the league ID via one of the following methods.
### Environment Variable
Specify your league ID using the `LEAGUE_ID` environment variable in your shell
```Shell
export LEAGUE_ID=123456789012345678
```
### Command-line Option
Use the `--league-id` or `-l` options followed by the league ID.
```Shell
python3 sleeper_log.py --league-id 123456789012345678
```

## AI Credit
The following models aided in the development of this project:  
`Claude Sonnet 4` `GPT-5`
