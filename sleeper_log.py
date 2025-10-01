import requests
import json
from datetime import datetime
from collections import defaultdict, Counter
import numpy as np
import os
import argparse
import subprocess

def get_git_commit_hash():
    """Get the current git commit hash"""
    try:
        result = subprocess.run(['git', 'rev-parse', '--short', 'HEAD'], 
                              capture_output=True, text=True, cwd=os.path.dirname(__file__))
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return "unknown"

class SleeperCLI:
    def __init__(self, league_id):
        self.league_id = league_id
        self.base_url = "https://api.sleeper.app/v1"
        self.league_data = None
        self.users = {}
        self.rosters = []
        self.matchups = {}
        self.players = {}
        self.current_week = 1
        self.max_week_with_data = 0
        self.draft_picks = []
        self.winners_bracket = []
        
    def fetch_league_data(self):
        """Fetch all necessary data from Sleeper API"""
        print("🏈 Fetching league data from Sleeper API...")
        
        # Get league info
        league_url = f"{self.base_url}/league/{self.league_id}"
        response = requests.get(league_url)
        if response.status_code != 200:
            raise Exception(f"❌ Failed to fetch league data: {response.status_code}")
        self.league_data = response.json()
        
        # Get current week
        state_url = f"{self.base_url}/state/nfl"
        state_response = requests.get(state_url)
        if state_response.status_code == 200:
            state_data = state_response.json()
            self.current_week = state_data.get('week', 1)
        
        # Get users
        print("👥 Fetching users...")
        users_url = f"{self.base_url}/league/{self.league_id}/users"
        users_response = requests.get(users_url)
        if users_response.status_code == 200:
            users_list = users_response.json()
            self.users = {user['user_id']: user for user in users_list}
        
        # Get rosters
        print("📋 Fetching rosters...")
        rosters_url = f"{self.base_url}/league/{self.league_id}/rosters"
        rosters_response = requests.get(rosters_url)
        if rosters_response.status_code == 200:
            self.rosters = rosters_response.json()
        
        # Get matchups (fetch all regular season weeks regardless of current NFL week)
        print("⚔️ Fetching matchups...")
        self.matchups = {}
        for week in range(1, 19):  # Weeks 1-18
            matchup_url = f"{self.base_url}/league/{self.league_id}/matchups/{week}"
            matchup_response = requests.get(matchup_url)
            if matchup_response.status_code == 200:
                week_data = matchup_response.json()
                if week_data:  # Only store weeks that have data
                    self.matchups[week] = week_data
                    self.max_week_with_data = max(self.max_week_with_data, week)
        
        # Get players
        print("🌟 Fetching player data...")
        players_url = f"{self.base_url}/players/nfl"
        players_response = requests.get(players_url)
        if players_response.status_code == 200:
            self.players = players_response.json()

        # Get winners bracket (playoffs)
        print("🏆 Fetching winners bracket...")
        wb_url = f"{self.base_url}/league/{self.league_id}/winners_bracket"
        wb_response = requests.get(wb_url)
        if wb_response.status_code == 200:
            try:
                self.winners_bracket = wb_response.json() or []
            except Exception:
                self.winners_bracket = []
        
        # Get draft data
        print("📋 Fetching draft data...")
        draft_url = f"{self.base_url}/league/{self.league_id}/drafts"
        draft_response = requests.get(draft_url)
        if draft_response.status_code == 200:
            try:
                drafts = draft_response.json()
                if drafts:
                    # Get the most recent draft
                    latest_draft = drafts[0]
                    draft_id = latest_draft.get('draft_id')
                    if draft_id:
                        picks_url = f"{self.base_url}/draft/{draft_id}/picks"
                        picks_response = requests.get(picks_url)
                        if picks_response.status_code == 200:
                            self.draft_picks = picks_response.json()
                        else:
                            self.draft_picks = []
                    else:
                        self.draft_picks = []
                else:
                    self.draft_picks = []
            except Exception:
                self.draft_picks = []
        else:
            self.draft_picks = []
        
        print("✅ Data fetch complete!")
    
    def get_team_name(self, roster_id):
        """Get team name for a roster"""
        roster = next((r for r in self.rosters if r['roster_id'] == roster_id), None)
        if not roster:
            return f"Team {roster_id}"
        
        user = self.users.get(roster['owner_id'])
        if not user:
            return f"Team {roster_id}"
        
        return (user.get('metadata', {}).get('team_name') or 
                user.get('display_name') or 
                user.get('username') or 
                f"Team {roster_id}")
    
    def get_player_name(self, player_id):
        """Get player name from player ID"""
        if not player_id or player_id not in self.players:
            return "Unknown Player"
        
        player = self.players[player_id]
        return f"{player.get('first_name', '')} {player.get('last_name', '')}".strip()
    
    def get_player_position_team(self, player_id):
        """Get player position and team"""
        if not player_id or player_id not in self.players:
            return "UNK", "UNK"
        
        player = self.players[player_id]
        return player.get('position', 'UNK'), player.get('team', 'UNK')
    
    def calculate_standings(self):
        """Calculate current standings"""
        standings = []
        
        for roster in self.rosters:
            team_name = self.get_team_name(roster['roster_id'])
            
            total_points = 0
            wins = roster.get('settings', {}).get('wins', 0)
            losses = roster.get('settings', {}).get('losses', 0)
            ties = roster.get('settings', {}).get('ties', 0)
            
            # Calculate points from matchups (only completed games)
            for week, week_matchups in self.matchups.items():
                for matchup in week_matchups:
                    if matchup['roster_id'] == roster['roster_id']:
                        points = matchup.get('points', 0)
                        # Only count points from completed games
                        if points > 0 and week <= self.max_week_with_data:
                            total_points += points
            
            standings.append({
                'team': team_name,
                'wins': wins,
                'losses': losses,
                'ties': ties,
                'points_for': total_points,
                'points_against': roster.get('settings', {}).get('fpts_against', 0)
            })
        
        standings.sort(key=lambda x: (x['wins'], x['points_for']), reverse=True)
        return standings
    
    def get_league_leaders(self):
        """Calculate league leaders"""
        standings = self.calculate_standings()
        
        highest_scorer = max(standings, key=lambda x: x['points_for'])
        lowest_scorer = min(standings, key=lambda x: x['points_for'])
        
        # Weekly performance analysis
        weekly_scores = defaultdict(list)
        weekly_highs = {}
        weekly_lows = {}
        
        for week, week_matchups in self.matchups.items():
            week_scores = []
            for matchup in week_matchups:
                team_name = self.get_team_name(matchup['roster_id'])
                points = matchup.get('points', 0)
                # Only include scores from completed games (both teams scored > 0 or week is completed)
                if points > 0 and week <= self.max_week_with_data:
                    weekly_scores[team_name].append(points)
                    week_scores.append((team_name, points))
            
            if week_scores:
                week_scores.sort(key=lambda x: x[1], reverse=True)
                weekly_highs[week] = week_scores[0]
                weekly_lows[week] = week_scores[-1]
        
        # Consistency analysis
        consistency_stats = {}
        for team, scores in weekly_scores.items():
            if scores:
                # Only use scores from completed games
                completed_scores = [s for s in scores if s > 0]
                if completed_scores:
                    consistency_stats[team] = {
                        'avg': np.mean(completed_scores),
                        'std': np.std(completed_scores),
                        'high': max(completed_scores),
                        'low': min(completed_scores)
                    }
        
        most_consistent = min(consistency_stats.items(), 
                            key=lambda x: x[1]['std']) if consistency_stats else None
        most_volatile = max(consistency_stats.items(),
                           key=lambda x: x[1]['std']) if consistency_stats else None
        
        # Calculate over/under performers based on wins vs points
        expected_wins = []
        for team in standings:
            team_name = team['team']
            actual_wins = team['wins']
            
            # Calculate expected wins based on points scored vs league
            better_records = sum(1 for other in standings if other['points_for'] > team['points_for'])
            expected_win_pct = 1 - (better_records / len(standings))
            games_played = team['wins'] + team['losses'] + team['ties']
            expected = expected_win_pct * games_played if games_played > 0 else 0
            
            expected_wins.append({
                'team': team_name,
                'actual_wins': actual_wins,
                'expected_wins': expected,
                'difference': actual_wins - expected,
                'games_played': games_played
            })
        
        # Sort by difference
        over_performers = sorted([t for t in expected_wins if t['difference'] > 0.5], 
                               key=lambda x: x['difference'], reverse=True)
        under_performers = sorted([t for t in expected_wins if t['difference'] < -0.5], 
                                key=lambda x: x['difference'])

        # Longest win and losing streaks
        def compute_streaks(sequence):
            max_win = max_lose = 0
            cur_win = cur_lose = 0
            for r in sequence:
                if r == 'W':
                    cur_win += 1
                    cur_lose = 0
                elif r == 'L':
                    cur_lose += 1
                    cur_win = 0
                else:
                    cur_win = 0
                    cur_lose = 0
                if cur_win > max_win:
                    max_win = cur_win
                if cur_lose > max_lose:
                    max_lose = cur_lose
            return max_win, max_lose

        longest_win_streak = None  # (team_name, length)
        longest_loss_streak = None  # (team_name, length)
        for roster in self.rosters:
            team_name = self.get_team_name(roster['roster_id'])
            seq = self.get_team_weekly_results(roster['roster_id'])
            win_len, lose_len = compute_streaks(seq)
            if win_len > 0:
                if not longest_win_streak or win_len > longest_win_streak[1]:
                    longest_win_streak = (team_name, win_len)
            if lose_len > 0:
                if not longest_loss_streak or lose_len > longest_loss_streak[1]:
                    longest_loss_streak = (team_name, lose_len)
        
        return {
            'highest_scorer': highest_scorer,
            'lowest_scorer': lowest_scorer,
            'most_consistent': most_consistent,
            'most_volatile': most_volatile,
            'weekly_highs': weekly_highs,
            'weekly_lows': weekly_lows,
            'consistency_stats': consistency_stats,
            'over_performers': over_performers,
            'under_performers': under_performers,
            'longest_win_streak': longest_win_streak,
            'longest_loss_streak': longest_loss_streak,
        }
    
    def create_ascii_header(self):
        """Create ASCII art header"""
        header = f"""
            /ZZ  \033[1mLEAGUE:\033[0m {self.league_data.get('name', '?'):<39}   /ZZ                    
           | ZZ  \033[1mSEASON:\033[0m {self.league_data.get('season', '?'):<41}| ZZ                    
   /ZZZZZZZ| ZZ  /ZZZZZZ   /ZZZZZZ   /ZZZZZZ   /ZZZZZZ   /ZZZZZZ  | ZZ  /ZZZZZZ   /ZZZZZZ 
  /ZZ_____/| ZZ /ZZ__  ZZ /ZZ__  ZZ /ZZ__  ZZ /ZZ__  ZZ /ZZ__  ZZ | ZZ /ZZ__  ZZ /ZZ__  ZZ
 |  ZZZZZZ | ZZ| ZZZZZZZZ| ZZZZZZZZ| ZZ  \ ZZ| ZZZZZZZZ| ZZ  \__/ | ZZ| ZZ  \ ZZ| ZZ  \ ZZ
  \____  ZZ| ZZ| ZZ_____/| ZZ_____/| ZZ  | ZZ| ZZ_____/| ZZ       | ZZ| ZZ  | ZZ| ZZ  | ZZ
  /ZZZZZZZ/| ZZ|  ZZZZZZZ|  ZZZZZZZ| ZZZZZZZ/|  ZZZZZZZ| ZZ       | ZZ|  ZZZZZZ/|  ZZZZZZZ
 |_______/ |__/ \_______/ \_______/| ZZ____/  \_______/|__//ZZZZZZ|__/ \______/  \____  ZZ
                                   | ZZ                   |______/               /ZZ  \ ZZ
                                   | ZZ  \033[1mGEN :\033[0m {datetime.now().strftime('%b %d, %Y @%I:%M %p'):<33}|  ZZZZZZ/
                                   |__/  \033[1mWEEK:\033[0m {self.current_week:0>2}                                \\______/
"""
        return header
    
    def get_team_weekly_results(self, roster_id):
        """Get win/loss results for each week for a team"""
        weekly_results = []
        
        for week in range(1, 18):  # 17 regular season weeks
            if week in self.matchups:
                week_matchups = self.matchups[week]
                
                # Find this team's matchup
                team_matchup = None
                for matchup in week_matchups:
                    if matchup['roster_id'] == roster_id:
                        team_matchup = matchup
                        break
                
                if team_matchup:
                    # Check if game has been played (both teams have scores > 0 or it's past the week)
                    team_points = team_matchup.get('points', 0)
                    matchup_id = team_matchup.get('matchup_id')
                    opponent_points = 0
                    
                    for matchup in week_matchups:
                        if (matchup.get('matchup_id') == matchup_id and 
                            matchup['roster_id'] != roster_id):
                            opponent_points = matchup.get('points', 0)
                            break
                    
                    # Only count as played if both teams have scores > 0 AND it's a completed week
                    if (team_points > 0 and opponent_points > 0) and week <= self.max_week_with_data:
                        # Determine win/loss
                        if team_points > opponent_points:
                            weekly_results.append('W')
                        elif team_points < opponent_points:
                            weekly_results.append('L')
                        else:
                            weekly_results.append('T')  # Tie
                    else:
                        weekly_results.append('-')  # Game not played yet
                else:
                    weekly_results.append('-')  # No game data
            else:
                weekly_results.append('-')  # Future week or no data
        
        return weekly_results

    def create_standings_table(self):
        """Create power rankings style standings with win/loss game log"""
        standings = self.calculate_standings()
        
        output = """
 /ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ[ - O X]
| ZZ                                                                                     ZZ
| ZZ                                    \033[1mSTANDINGS\033[0m                                        ZZ
| ZZ                                                                                     ZZ
| ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ
|_________________________________________________________________________________________/

      Rnk|Team         |1 |2 |3 |4 |5 |6 |7 |8 |9 |10|11|12|13|14|15|16|17|Rec |Pnts"""
        
        for i, team in enumerate(standings):
            rank = i + 1
            team_name = team['team'][:12]  # Truncate to align with header 'Team Name'
            
            # Get roster for this team to find weekly results
            roster = next((r for r in self.rosters if self.get_team_name(r['roster_id']) == team['team']), None)
            
            if roster:
                weekly_results = self.get_team_weekly_results(roster['roster_id'])
            else:
                weekly_results = ['-'] * 17
            
            # Create colored game log (17 segments, 2 chars each) and delimit with '|'
            game_blocks = []
            for week_result in weekly_results:
                if week_result == 'W':
                    game_blocks.append("\033[92m██\033[0m")  # Green blocks
                elif week_result == 'L':
                    game_blocks.append("\033[91m██\033[0m")  # Red blocks
                elif week_result == 'T':
                    game_blocks.append("\033[93m██\033[0m")  # Yellow blocks for tie
                else:
                    game_blocks.append("░░")  # Gray blocks for no game/future
            game_log = "|".join(game_blocks) + "|"
            
            # Create record string
            record = f"{team['wins']}-{team['losses']}"
            if team['ties'] > 0:
                record += f"-{team['ties']}"
            
            # Add rank display (left-justified in two spaces)
            rank_display = f"#{rank:<2}"
            
            points_str = f"{team['points_for']:06.1f}"
            output += (
                f"\n      {rank_display}|{team_name:<12} |{game_log}"
                f"{record:<4}|{points_str:<6}"
            )
        
        output += "\n"
        return output
    
    def convert_ansi_to_html(self, text):
        """Convert ANSI color codes to HTML spans"""
        # Replace ANSI color codes with HTML
        text = text.replace('\033[92m', '<span style="color: #00ff00;">')  # Green
        text = text.replace('\033[91m', '<span style="color: #ff0000;">')  # Red  
        text = text.replace('\033[93m', '<span style="color: #ffff00;">')  # Yellow
        text = text.replace('\033[32m', '<span style="color: #00ff00;">')  # Green (32)
        # Bold start/end
        text = text.replace('\033[1m', '<b>')
        # Reset closes bold and color span if present
        text = text.replace('\033[0m', '</b></span>')
        
        # Convert spaces to non-breaking spaces to preserve alignment
        # Replace multiple spaces with &nbsp; to maintain spacing
        import re
        text = re.sub(r' {2,}', lambda m: '&nbsp;' * len(m.group()), text)
        
        return text
    
    def generate_html_report(self, filename="sleeper_report.html"):
        """Generate HTML version of the report for web viewing"""
        print("Generating HTML report...")
        
        # Get the text report
        text_report = ""
        text_report += self.create_ascii_header()
        text_report += self.create_standings_table()
        text_report += self.create_leaders_section()
        text_report += self.create_roster_section()
        text_report += self.create_schedule_section()
        text_report += self.create_playoff_picture()
        text_report += self.create_draft_summary()
        
        # Footer
        commit_hash = get_git_commit_hash()
        text_report += f"""
 /ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ[ - O X]
| ZZ                                                                                     ZZ
| ZZ                      Generated by \033[1msleeper_log\033[0m commit \033[1m#{commit_hash}\033[0m                       ZZ
| ZZ                      https://github.com/keithalbe/sleeper_log                       ZZ
| ZZ                      Vibe coded with: \033[1mSonnet 4\033[0m, \033[1mGPT-5\033[0m, \033[1mCursor\033[0m                       ZZ
| ZZ                                                                                     ZZ
| ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ
|_________________________________________________________________________________________/
"""
        
        # Convert ANSI colors to HTML
        html_content = self.convert_ansi_to_html(text_report)
        
        # Wrap in HTML
        full_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{self.league_data.get('name', 'Fantasy League')} - sleeper-cli Report</title>
    <style>
        body {{
            font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', 'Consolas', 'Courier New', monospace;
            background-color: #0d1117;
            color: #c9d1d9;
            margin: 20px;
            padding: 20px;
            line-height: 1.2;
            font-size: 13px;
        }}
        
        pre {{
            white-space: pre;
            margin: 0;
            padding: 0;
            overflow-x: auto;
        }}
        
        /* GitHub-style terminal colors */
        .terminal {{
            background-color: #161b22;
            border: 1px solid #30363d;
            border-radius: 8px;
            padding: 20px;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
        }}
        
        /* Custom styles for better readability */
        .header {{
            color: #58a6ff;
            font-weight: bold;
        }}
        
        .emoji {{
            font-size: 1.1em;
        }}
        
        /* Ensure Unicode characters render properly */
        .blocks {{
            letter-spacing: -0.1em;
        }}
        
        @media (max-width: 768px) {{
            body {{
                margin: 10px;
                padding: 10px;
                font-size: 11px;
            }}
        }}
    </style>
</head>
<body>
    <div class="terminal">
        <pre class="blocks">{html_content}</pre>
    </div>
    
    <script>
        // Add some interactivity
        document.addEventListener('DOMContentLoaded', function() {{
            console.log('sleeper-cli HTML report loaded 🏈');
        }});
    </script>
</body>
</html>"""
        
        # Save HTML file
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(full_html)
        
        print(f"🌐 HTML report saved to: {filename}")
        print(f"   Open in Safari: open {filename}")
        
        return filename
    
    def get_rank_emoji(self, rank):
        """Get emoji for ranking"""
        if rank == 1:
            return "🥇"
        elif rank == 2:
            return "🥈"
        elif rank == 3:
            return "🥉"
        elif rank <= 6:
            return "✅"
        else:
            return "💀"
    
    def create_leaders_section(self):
        """Create league leaders section"""
        leaders = self.get_league_leaders()
        
        output = """
 /ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ[ - O X]
| ZZ                                                                                     ZZ
| ZZ                                  \033[1mLEAGUE ANALYTICS\033[0m                                   ZZ
| ZZ                                                                                     ZZ
| ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ
|_________________________________________________________________________________________/

"""
        
        # Highest Scorer
        if leaders['highest_scorer']:
            hs = leaders['highest_scorer']
            output += f"     🔥 HIGHEST SCORER: {hs['team']}\n"
            output += f"        └─ {hs['points_for']:.1f} total points\n\n"
        
        # Most Consistent
        if leaders['most_consistent']:
            team, stats = leaders['most_consistent']
            output += f"     🪨 MOST CONSISTENT: {team}\n"
            output += f"        └─ {stats['avg']:.1f} avg ± {stats['std']:.1f} std dev\n\n"
        
        # Most Volatile
        if leaders['most_volatile']:
            team, stats = leaders['most_volatile']
            output += f"     🎢 BOOM OR BUST: {team}\n"
            output += f"        └─ {stats['high']:.1f} high, {stats['low']:.1f} low (±{stats['std']:.1f})\n\n"
        
        # Over-performers
        if leaders['over_performers']:
            output += "     🚀 OVER-PERFORMERS (Lucky with record vs points):\n"
            for perf in leaders['over_performers'][:3]:  # Top 3
                output += f"        {perf['team'][:25]}: {perf['actual_wins']}-{perf['games_played']-perf['actual_wins']} record (+{perf['difference']:.1f} wins above expected)\n"
            output += "\n"
        
        # Under-performers  
        if leaders['under_performers']:
            output += "     😤 UNDER-PERFORMERS (Unlucky with record vs points):\n"
            for perf in leaders['under_performers'][:3]:  # Bottom 3
                output += f"        {perf['team'][:25]}: {perf['actual_wins']}-{perf['games_played']-perf['actual_wins']} record ({perf['difference']:.1f} wins below expected)\n"
            output += "\n"

        # Streaks
        if leaders.get('longest_win_streak'):
            team, length = leaders['longest_win_streak']
            output += f"     🔥 LONGEST WIN STREAK: {team} — {length} in a row\n"
        if leaders.get('longest_loss_streak'):
            team, length = leaders['longest_loss_streak']
            output += f"     💤 LONGEST LOSING STREAK: {team} — {length} in a row\n"
        if leaders.get('longest_win_streak') or leaders.get('longest_loss_streak'):
            output += "\n"
        
        # Weekly highs
        if leaders['weekly_highs']:
            output += "     🚀 WEEKLY HIGH SCORES:\n"
            for week, (team, score) in sorted(leaders['weekly_highs'].items()):
                # Show only weeks we have data for
                if self.max_week_with_data and week <= self.max_week_with_data:
                    output += f"        └─ Week {week:2}: {team[:20]} ({score:.1f} pts)\n"
            
        
        # Advanced Stats
        if leaders['consistency_stats']:
            all_averages = [stats['avg'] for stats in leaders['consistency_stats'].values()]
            league_average = np.mean(all_averages)
            
            output += f"     📊 LEAGUE AVERAGE SCORE: {league_average:.1f} points\n"
            
            # Teams above/below average
            above_avg = sum(1 for avg in all_averages if avg > league_average)
            below_avg = len(all_averages) - above_avg
            
            output += f"     📈 TEAMS ABOVE AVERAGE: {above_avg}\n"
            output += f"     📉 TEAMS BELOW AVERAGE: {below_avg}\n"
            output += "\n"
            
            
            # Score distribution
            all_scores = []
            for stats in leaders['consistency_stats'].values():
                all_scores.extend([stats['high'], stats['low']])
            
            if all_scores:
                output += f"     🎯 League High Score: {max(all_scores):.1f}\n"
                output += f"     💀 League Low Score: {min(all_scores):.1f}\n"
                output += f"     📊 Score Range: {max(all_scores) - min(all_scores):.1f} points\n"
                
        
        # Matchup records
        total_matchups = sum(len(matchups) // 2 for matchups in self.matchups.values())
        output += f"     ⚔️ Total Matchups Played: {total_matchups}{'':<60}\n"
        
        return output
    
    def get_player_stats(self, player_id, roster_id):
        """Get player's last week points and projection for upcoming week"""
        last_week_points = 0
        projection = 0
        
        # Get last week's points based on data availability
        last_completed_week = (self.max_week_with_data or self.current_week) - 1
        if last_completed_week >= 1 and last_completed_week in self.matchups:
            last_week_matchups = self.matchups[last_completed_week]
            for matchup in last_week_matchups:
                if matchup['roster_id'] == roster_id:
                    players_points = matchup.get('players_points', {})
                    last_week_points = players_points.get(player_id, 0)
                    break
        
        # For projections, use the most recent week with data for this player
        # Look through all weeks to find the most recent non-zero score
        for week in sorted(self.matchups.keys(), reverse=True):
            if week in self.matchups:
                week_matchups = self.matchups[week]
                for matchup in week_matchups:
                    if matchup['roster_id'] == roster_id:
                        players_points = matchup.get('players_points', {})
                        player_points = players_points.get(player_id, 0)
                        if player_points > 0:
                            projection = player_points
                            return last_week_points, projection
        
        # If no historical data, use last week's points as projection
        projection = last_week_points if last_week_points > 0 else 0.0
        
        return last_week_points, projection
    
    def create_roster_section(self):
        """Create team rosters section with side-by-side format"""
        output = """
 /ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ[ - O X]
| ZZ                                                                                     ZZ
| ZZ                                \033[1mTEAM ROSTERS\033[0m                                         ZZ
| ZZ                                                                                     ZZ
| ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ
|_________________________________________________________________________________________/

"""
        
        for roster in self.rosters:
            team_name = self.get_team_name(roster['roster_id'])
            
            players = roster.get('players', []) or []
            starters = roster.get('starters', []) or []
            taxi = roster.get('taxi', []) or []
            reserve = roster.get('reserve', []) or []  # IR
            
            if not players:
                output += f"      \033[1m{team_name.upper()}\033[0m (0.0 pts)\n"
                output += "      " + "─" * 79 + "\n"
                output += "      No players found\n\n"
                continue
            
            # Group all players by position
            all_players = players + (reserve or [])
            players_by_position = defaultdict(list)
            
            for player_id in all_players:
                if player_id:
                    player_name = self.get_player_name(player_id)
                    position, nfl_team = self.get_player_position_team(player_id)
                    last_points, projection = self.get_player_stats(player_id, roster['roster_id'])
                    
                    # Mark IR players
                    if reserve and player_id in reserve:
                        player_name = f"{player_name} (IR)"
                    
                    players_by_position[position].append({
                        'name': player_name,
                        'team': nfl_team,
                        'points': last_points,
                        'projection': projection,
                        'is_starter': player_id in (starters or [])
                    })
            
            # Sort players within each position (starters first, then by points)
            for pos in players_by_position:
                players_by_position[pos].sort(key=lambda x: (not x['is_starter'], -(x['points'] or 0)), reverse=False)
            
            # Display by position
            position_order = ['QB', 'RB', 'WR', 'TE', 'FLX', 'K', 'DEF']
            total_starter_points = 0
            
            for pos in position_order:
                if pos in players_by_position:
                    players_in_pos = players_by_position[pos]
                    if not players_in_pos:
                        continue
                    
                    # Position header
                    pos_display = 'DEF' if pos == 'DEF' else pos
                    output += f"      {pos_display:<3} :: "
                    
                    # Group players into lines of 3
                    for i, player in enumerate(players_in_pos):
                        if i > 0 and i % 3 == 0:
                            # New line, indent to align with names
                            output += "\n      " + " " * 7
                        
                        # Format player name and projection
                        name = player['name'][:15]  # Allow longer names
                        projection = player['projection'] if isinstance(player['projection'], (int, float)) else 0.0
                        proj_str = f"({projection:03.1f})"
                        
                        # Color the starter green and bold
                        if player['is_starter']:
                            padded_name = f"\033[1m\033[32m{name:<15}\033[0m"  # Bold green
                            total_starter_points += projection
                        else:
                            padded_name = f"{name:<15}"
                        
                        # Add player to line with proper alignment (fixed width for names and projections)
                        # Pad the name to 20 characters, then add the projection
                        if i % 3 == 2:  # Last player on line
                            output += f"{padded_name} {proj_str:<6}"
                        else:  # Not last player, add spacing
                            output += f"{padded_name} {proj_str:<6}  "
                    
                    output += "\n"
            
            # Handle other positions not in the main order
            for pos, players_in_pos in players_by_position.items():
                if pos not in position_order and players_in_pos:
                    output += f"      {pos:<3} :: "
                    
                    for i, player in enumerate(players_in_pos):
                        if i > 0 and i % 3 == 0:
                            output += "\n      " + " " * 7
                        
                        name = player['name'][:15]
                        projection = player['projection'] if isinstance(player['projection'], (int, float)) else 0.0
                        proj_str = f"({projection:04.1f})"
                        
                        if player['is_starter']:
                            name = f"\033[1m\033[32m{name}\033[0m"  # Bold green
                            total_starter_points += projection
                        
                        # Pad the name to 20 characters, then add the projection
                        padded_name = f"{name:<20}"
                        if i % 3 == 2:
                            output += f"{padded_name} {proj_str:<8}"
                        else:
                            output += f"{padded_name} {proj_str:<8}  "
                    
                    output += "\n"
            
            # Print team name header with projection after calculating total
            output += f"      \033[1m{team_name.upper()}\033[0m ({total_starter_points:.1f} pts)\n\n"
            
            # TAXI (for dynasty leagues) - full width
            if taxi:
                output += f"      >> TAXI SQUAD :: {team_name.upper()}\n"
                output += "      " + "─" * 47 + "\n"
                
                for player_id in taxi:
                    player_name = self.get_player_name(player_id)[:15]
                    position, nfl_team = self.get_player_position_team(player_id)
                    last_points, projection = self.get_player_stats(player_id, roster['roster_id'])
                    
                    display_pos = 'DST' if position == 'DEF' else position
                    taxi_points = last_points if isinstance(last_points, (int, float)) else 0.0
                    nfl_team_disp = nfl_team if isinstance(nfl_team, str) and nfl_team else '---'
                    output += f"      {display_pos:<4} :: {player_name:<15} ({nfl_team_disp:>3}) {taxi_points:>5.1f}\n"
                
                output += "      " + "─" * 47 + "\n\n"
            
        return output
    
    def create_fun_stats(self):
        """Create fun/nerdy statistics section"""
        leaders = self.get_league_leaders()
        
        output = """
 /ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ
| ZZ                                                                                     ZZ
| ZZ                                 \033[1mADVANCED STATS\033[0m                                      ZZ
| ZZ                                                                                     ZZ
| ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ
|_________________________________________________________________________________________/

"""
        
        # Calculate some fun stats
        if leaders['consistency_stats']:
            all_averages = [stats['avg'] for stats in leaders['consistency_stats'].values()]
            league_average = np.mean(all_averages)
            
            output += f"📊 League Average Score: {league_average:.1f} points\n"
            
            # Teams above/below average
            above_avg = sum(1 for avg in all_averages if avg > league_average)
            below_avg = len(all_averages) - above_avg
            
            output += f"📈 Teams Above Average: {above_avg}\n"
            output += f"📉 Teams Below Average: {below_avg}\n\n"
            
            # Score distribution
            all_scores = []
            for stats in leaders['consistency_stats'].values():
                all_scores.extend([stats['high'], stats['low']])
            
            if all_scores:
                output += f"🎯 League High Score: {max(all_scores):.1f}\n"
                output += f"💀 League Low Score: {min(all_scores):.1f}\n"
                output += f"📊 Score Range: {max(all_scores) - min(all_scores):.1f} points\n\n"
        
        # Matchup records
        total_matchups = sum(len(matchups) // 2 for matchups in self.matchups.values())
        output += f"⚔️ Total Matchups Played: {total_matchups}\n"
        
        return output
    
    def create_playoff_picture(self):
        """Render playoff teams and bracket picture if available"""
        output = """
 /ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ[ - O X]
| ZZ                                                                                     ZZ
| ZZ                                 \033[1mPLAYOFF PICTURE\033[0m                                     ZZ
| ZZ                                                                                     ZZ
| ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ
|_________________________________________________________________________________________/

"""

        if not self.winners_bracket:
            output += "      No playoff bracket data available.\n\n"
            return output

        # Build seed map from standings order (best to worst)
        standings = self.calculate_standings()
        team_to_seed = {t['team']: i + 1 for i, t in enumerate(standings)}
        rosterid_to_team = {r['roster_id']: self.get_team_name(r['roster_id']) for r in self.rosters}

        # Index bracket by round then matchup_id
        rounds = defaultdict(list)
        for g in self.winners_bracket:
            rounds[g.get('round', 0)].append(g)

        def score_for_week(roster_id: int, week: int) -> float:
            if week in self.matchups:
                for m in self.matchups[week]:
                    if m.get('roster_id') == roster_id:
                        return float(m.get('points', 0) or 0)
            return 0.0

        # Render each round
        for rnd in sorted(rounds.keys()):
            games = sorted(rounds[rnd], key=lambda x: x.get('matchup_id', 0))
            for g in games:
                t1 = rosterid_to_team.get(g.get('t1'), f"R{g.get('t1')}")
                t2 = rosterid_to_team.get(g.get('t2'), f"R{g.get('t2')}")
                week = g.get('week') or 0
                s1 = score_for_week(g.get('t1'), week)
                s2 = score_for_week(g.get('t2'), week)
                winner_roster = g.get('w')
                winner_team = rosterid_to_team.get(winner_roster, '?')
                seed1 = team_to_seed.get(t1, '-')
                seed2 = team_to_seed.get(t2, '-')
                # Truncate team names to 15 characters
                t1_short = t1[:15]
                t2_short = t2[:15]
                winner_short = winner_team[:15]
                line = f"      ({seed1}) {t1_short:<15} {s1:>6.1f}  vs  ({seed2}) {t2_short:<15} {s2:>6.1f}  =>  \033[1m{winner_short}\033[0m\n"
                output += line
            output += "\n"

        return output
    
    def create_draft_summary(self):
        """Create draft summary section"""
        output = """
 /ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ[ - O X]
| ZZ                                                                                     ZZ
| ZZ                                  \033[1mDRAFT SUMMARY\033[0m                                      ZZ
| ZZ                                                                                     ZZ
| ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ
|_________________________________________________________________________________________/

"""
        
        if not self.draft_picks:
            output += "      No draft data available.\n\n"
            return output
        
        # Group picks by team
        picks_by_team = defaultdict(list)
        for pick in self.draft_picks:
            roster_id = pick.get('roster_id')
            if roster_id:
                picks_by_team[roster_id].append(pick)
        
        # Sort picks by round and pick number
        for roster_id in picks_by_team:
            picks_by_team[roster_id].sort(key=lambda x: (x.get('round', 0), x.get('pick_no', 0)))
        
        # Display picks by team
        for roster_id in sorted(picks_by_team.keys()):
            team_name = self.get_team_name(roster_id)
            picks = picks_by_team[roster_id]
            
            output += f"      \033[1m{team_name.upper()}\033[0m\n"
            
            # Group picks into lines of 3
            for i in range(0, len(picks), 3):
                line_picks = picks[i:i+3]
                line = "      "
                
                for pick in line_picks:
                    round_num = pick.get('round', 0)
                    pick_num = pick.get('pick_no', 0)
                    player_id = pick.get('player_id')
                    
                    if player_id and player_id in self.players:
                        player_name = self.players[player_id].get('full_name', 'Unknown')[:12]
                        position = "(" + self.players[player_id].get('position', 'UNK') + ")"
                        line += f"R{round_num:<02}.{pick_num:03d} {player_name:<12} {position:<5} "
                    else:
                        line += f"R{round_num:<02}.{pick_num:03d} {'Unknown':<12} (UNK) "
                
                output += line.rstrip() + "\n"
            
            output += "\n"
        
        return output
    
    def create_schedule_section(self):
        """Create schedule section showing weekly matchups"""
        output = """
 /ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ[ - O X]
| ZZ                                                                                     ZZ
| ZZ                                   \033[1mSCHEDULE\033[0m                                         ZZ
| ZZ                                                                                     ZZ
| ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ
|_________________________________________________________________________________________/

"""
        
        if not self.matchups:
            output += "      No schedule data available.\n\n"
            return output
        
        # Display each week's matchups
        for week in sorted(self.matchups.keys()):
            week_matchups = self.matchups[week]
            if not week_matchups:
                continue
                
            output += f"      \033[1mWeek {week}\033[0m\n"
            
            # Group matchups by matchup_id
            matchup_groups = defaultdict(list)
            for matchup in week_matchups:
                matchup_id = matchup.get('matchup_id')
                if matchup_id is not None:
                    matchup_groups[matchup_id].append(matchup)
            
            # Display each matchup
            for matchup_id in sorted(matchup_groups.keys()):
                matchup_teams = matchup_groups[matchup_id]
                if len(matchup_teams) >= 2:
                    team1 = matchup_teams[0]
                    team2 = matchup_teams[1]
                    
                    team1_name = self.get_team_name(team1['roster_id'])[:25]
                    team2_name = self.get_team_name(team2['roster_id'])[:25]
                    
                    team1_points = team1.get('points', 0)
                    team2_points = team2.get('points', 0)
                    
                    # Color the winner
                    if team1_points > team2_points:
                        output += f"      \033[1m\033[32m{team1_name:<25}\033[0m {team1_points:>6.1f}  vs  {team2_name:<25} {team2_points:>6.1f}\n"
                    elif team2_points > team1_points:
                        output += f"      {team1_name:<25} {team1_points:>6.1f}  vs  \033[1m\033[32m{team2_name:<25}\033[0m {team2_points:>6.1f}\n"
                    else:
                        output += f"      {team1_name:<25} {team1_points:>6.1f}  vs  {team2_name:<25} {team2_points:>6.1f}\n"

            output += "\n"
        
        return output

def main():
    print("""
                    
    🏈 Fantasy Football Report Generator 🏆
    
    """)
    
    # Accept the league ID via the --league_id flag or an environment variable
    parser = argparse.ArgumentParser(description="Generate Sleeper fantasy football reports")
    parser.add_argument("--league-id", "-l", dest="league_id", help="Sleeper league ID (overrides LEAGUE_ID env var)")
    args = parser.parse_args()
    
    league_id = args.league_id or os.getenv("LEAGUE_ID")
    if not league_id:
        print("No league ID provided. Set LEAGUE_ID env var or pass --league-id.")
        print("Example (zsh): export LEAGUE_ID=123456789012345678")
        print("Or run: python sleeper_log.py --league-id 123456789012345678")
        return
    
    try:
        # Create report generator
        cli = SleeperCLI(league_id)
        
        # Fetch all data
        cli.fetch_league_data()
        
        # Generate HTML report
        cli.generate_html_report()
        
        print("\nReport generation complete! See sleeper_log.html")
        
    except Exception as e:
        print(f"❌ Error generating report: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
