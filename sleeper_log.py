import requests
import json
from datetime import datetime
from collections import defaultdict, Counter
import numpy as np
import os
import argparse

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
        
        # Get matchups
        print("⚔️ Fetching matchups...")
        for week in range(1, min(self.current_week + 1, 19)):
            matchup_url = f"{self.base_url}/league/{self.league_id}/matchups/{week}"
            matchup_response = requests.get(matchup_url)
            if matchup_response.status_code == 200:
                self.matchups[week] = matchup_response.json()
        
        # Get players
        print("🌟 Fetching player data...")
        players_url = f"{self.base_url}/players/nfl"
        players_response = requests.get(players_url)
        if players_response.status_code == 200:
            self.players = players_response.json()
        
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
            
            # Calculate points from matchups
            for week_matchups in self.matchups.values():
                for matchup in week_matchups:
                    if matchup['roster_id'] == roster['roster_id']:
                        total_points += matchup.get('points', 0)
            
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
                consistency_stats[team] = {
                    'avg': np.mean(scores),
                    'std': np.std(scores),
                    'high': max(scores),
                    'low': min(scores)
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
        
        return {
            'highest_scorer': highest_scorer,
            'lowest_scorer': lowest_scorer,
            'most_consistent': most_consistent,
            'most_volatile': most_volatile,
            'weekly_highs': weekly_highs,
            'weekly_lows': weekly_lows,
            'consistency_stats': consistency_stats,
            'over_performers': over_performers,
            'under_performers': under_performers
        }
    
    def create_ascii_header(self):
        """Create ASCII art header"""
        header = f"""
           /ZZ                                                    /ZZ                    
          | ZZ                                                   | ZZ                    
  /ZZZZZZZ| ZZ  /ZZZZZZ   /ZZZZZZ   /ZZZZZZ   /ZZZZZZ   /ZZZZZZ  | ZZ  /ZZZZZZ   /ZZZZZZ 
 /ZZ_____/| ZZ /ZZ__  ZZ /ZZ__  ZZ /ZZ__  ZZ /ZZ__  ZZ /ZZ__  ZZ | ZZ /ZZ__  ZZ /ZZ__  ZZ
|  ZZZZZZ | ZZ| ZZZZZZZZ| ZZZZZZZZ| ZZ  \ ZZ| ZZZZZZZZ| ZZ  \__/ | ZZ| ZZ  \ ZZ| ZZ  \ ZZ
 \____  ZZ| ZZ| ZZ_____/| ZZ_____/| ZZ  | ZZ| ZZ_____/| ZZ       | ZZ| ZZ  | ZZ| ZZ  | ZZ
 /ZZZZZZZ/| ZZ|  ZZZZZZZ|  ZZZZZZZ| ZZZZZZZ/|  ZZZZZZZ| ZZ       | ZZ|  ZZZZZZ/|  ZZZZZZZ
|_______/ |__/ \_______/ \_______/| ZZ____/  \_______/|__//ZZZZZZ|__/ \______/  \____  ZZ
                                  | ZZ                   |______/               /ZZ  \ ZZ
                                  | ZZ                                         |  ZZZZZZ/
                                  |__/                                          \______/ 

🏟️ League: {self.league_data.get('name', 'Fantasy League')}
📅 Season: {self.league_data.get('season', '2024')}
⏰ Generated: {datetime.now().strftime('%B %d, %Y at %I:%M` %p')}
📊 Current Week: {self.current_week}

"""
        return header
    
    def get_team_weekly_results(self, roster_id):
        """Get win/loss results for each week for a team"""
        weekly_results = []
        
        for week in range(1, 17):  # 16 regular season weeks
            if week in self.matchups:
                week_matchups = self.matchups[week]
                
                # Find this team's matchup
                team_matchup = None
                for matchup in week_matchups:
                    if matchup['roster_id'] == roster_id:
                        team_matchup = matchup
                        break
                
                if team_matchup:
                    # Find opponent's score
                    matchup_id = team_matchup.get('matchup_id')
                    team_points = team_matchup.get('points', 0)
                    opponent_points = 0
                    
                    for matchup in week_matchups:
                        if (matchup.get('matchup_id') == matchup_id and 
                            matchup['roster_id'] != roster_id):
                            opponent_points = matchup.get('points', 0)
                            break
                    
                    # Determine win/loss
                    if team_points > opponent_points:
                        weekly_results.append('W')
                    elif team_points < opponent_points:
                        weekly_results.append('L')
                    else:
                        weekly_results.append('T')  # Tie
                else:
                    weekly_results.append('-')  # No game data
            else:
                weekly_results.append('-')  # Future week or no data
        
        return weekly_results

    def create_standings_table(self):
        """Create power rankings style standings with win/loss game log"""
        standings = self.calculate_standings()
        
        output = """
┌─────────────────────────────────────────────────────────────────────────────┐
│                          🏆 POWER RANKINGS 🏆                              │
└─────────────────────────────────────────────────────────────────────────────┘

>> POWER RANKINGS
─────────────────────────────────────────────────────────────────────────────────
    Team Name      1  2  3  4  5  6  7  8  9 10 11 12 13 14 15 16  Record   Points
─────────────────────────────────────────────────────────────────────────────────
"""
        
        for i, team in enumerate(standings):
            rank = i + 1
            team_name = team['team'][:13]  # Truncate long names
            
            # Get roster for this team to find weekly results
            roster = next((r for r in self.rosters if self.get_team_name(r['roster_id']) == team['team']), None)
            
            if roster:
                weekly_results = self.get_team_weekly_results(roster['roster_id'])
            else:
                weekly_results = ['-'] * 16
            
            # Create colored game log (16 segments, 3 chars each)
            game_log = ""
            for week_result in weekly_results:
                if week_result == 'W':
                    game_log += "\033[92m███\033[0m"  # Green blocks
                elif week_result == 'L':
                    game_log += "\033[91m███\033[0m"  # Red blocks  
                elif week_result == 'T':
                    game_log += "\033[93m███\033[0m"  # Yellow blocks for tie
                else:
                    game_log += "░░░"  # Gray blocks for no game/future
            
            # Create record string
            record = f"{team['wins']}-{team['losses']}"
            if team['ties'] > 0:
                record += f"-{team['ties']}"
            
            # Add rank display
            if rank == 1:
                rank_display = "#1 "
            elif rank == 2:
                rank_display = "#2 " 
            elif rank == 3:
                rank_display = "#3 "
            else:
                rank_display = f"#{rank:2}"
            
            output += f"{rank_display} {team_name:<13} {game_log} {record:>6} {team['points_for']:>7.1f}\n"
        
        output += "─────────────────────────────────────────────────────────────────────────────────\n"
        
        return output
    
    def convert_ansi_to_html(self, text):
        """Convert ANSI color codes to HTML spans"""
        # Replace ANSI color codes with HTML
        text = text.replace('\033[92m', '<span style="color: #00ff00;">')  # Green
        text = text.replace('\033[91m', '<span style="color: #ff0000;">')  # Red  
        text = text.replace('\033[93m', '<span style="color: #ffff00;">')  # Yellow
        text = text.replace('\033[0m', '</span>')  # Reset
        return text
    
    def generate_html_report(self, filename="sleeper_report.html"):
        """Generate HTML version of the report for web viewing"""
        print("🌐 Generating HTML report...")
        
        # Get the text report
        text_report = ""
        text_report += self.create_ascii_header()
        text_report += self.create_standings_table()
        text_report += self.create_leaders_section()
        text_report += self.create_fun_stats()
        text_report += self.create_roster_section()
        
        # Footer
        text_report += f"""

┌─────────────────────────────────────────────────────────────────────────────┐
│                     Generated by sleeper-cli v1.0 🔥                       │
│                        Keep grinding, fantasy legends! 🏆                   │
└─────────────────────────────────────────────────────────────────────────────┘

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
┌─────────────────────────────────────────────────────────────────────────────┐
│                           🌟 LEAGUE LEADERS 🌟                             │
└─────────────────────────────────────────────────────────────────────────────┘

"""
        
        # Highest Scorer
        if leaders['highest_scorer']:
            hs = leaders['highest_scorer']
            output += f"🔥 HIGHEST SCORER: {hs['team']}\n"
            output += f"   └─ {hs['points_for']:.1f} total points\n\n"
        
        # Most Consistent
        if leaders['most_consistent']:
            team, stats = leaders['most_consistent']
            output += f"📈 MOST CONSISTENT: {team}\n"
            output += f"   └─ {stats['avg']:.1f} avg ± {stats['std']:.1f} std dev\n\n"
        
        # Most Volatile
        if leaders['most_volatile']:
            team, stats = leaders['most_volatile']
            output += f"🎢 BOOM OR BUST: {team}\n"
            output += f"   └─ {stats['high']:.1f} high, {stats['low']:.1f} low (±{stats['std']:.1f})\n\n"
        
        # Over-performers
        if leaders['over_performers']:
            output += "🚀 OVER-PERFORMERS (Lucky with record vs points):\n"
            for perf in leaders['over_performers'][:3]:  # Top 3
                output += f"   {perf['team'][:25]}: {perf['actual_wins']}-{perf['games_played']-perf['actual_wins']} record (+{perf['difference']:.1f} wins above expected)\n"
            output += "\n"
        
        # Under-performers  
        if leaders['under_performers']:
            output += "😤 UNDER-PERFORMERS (Unlucky with record vs points):\n"
            for perf in leaders['under_performers'][:3]:  # Bottom 3
                output += f"   {perf['team'][:25]}: {perf['actual_wins']}-{perf['games_played']-perf['actual_wins']} record ({perf['difference']:.1f} wins below expected)\n"
            output += "\n"
        
        # Weekly highs
        if leaders['weekly_highs']:
            output += "🚀 WEEKLY HIGH SCORES:\n"
            for week, (team, score) in sorted(leaders['weekly_highs'].items()):
                if week <= self.current_week:
                    output += f"   Week {week:2}: {team[:20]} ({score:.1f} pts)\n"
            output += "\n"
        
        return output
    
    def get_player_stats(self, player_id, roster_id):
        """Get player's last week points and projection for upcoming week"""
        last_week_points = 0
        projection = 0
        
        # Get last week's points
        if self.current_week > 1 and (self.current_week - 1) in self.matchups:
            last_week_matchups = self.matchups[self.current_week - 1]
            for matchup in last_week_matchups:
                if matchup['roster_id'] == roster_id:
                    players_points = matchup.get('players_points', {})
                    last_week_points = players_points.get(player_id, 0)
                    break
        
        # Note: Sleeper API doesn't provide projections directly
        # You'd need a third-party service for projections
        # For now, we'll show "N/A" for projections
        
        return last_week_points, "N/A"
    
    def create_roster_section(self):
        """Create team rosters section with side-by-side format"""
        output = """
┌─────────────────────────────────────────────────────────────────────────────┐
│                           👥 TEAM ROSTERS 👥                               │
└─────────────────────────────────────────────────────────────────────────────┘

"""
        
        for roster in self.rosters:
            team_name = self.get_team_name(roster['roster_id'])
            
            players = roster.get('players', []) or []
            starters = roster.get('starters', []) or []
            taxi = roster.get('taxi', []) or []
            reserve = roster.get('reserve', []) or []  # IR
            
            if not players:
                output += f">> {team_name.upper()}\n"
                output += "─" * 79 + "\n"
                output += "No players found\n\n"
                continue
            
            # Prepare starters data
            starter_lines = []
            total_starter_points = 0
            
            if starters:
                starter_positions = ['QB', 'RB', 'RB', 'WR', 'WR', 'TE', 'FLEX', 'K', 'DEF']
                if len(starters) < len(starter_positions):
                    starter_positions = starter_positions[:len(starters)]
                
                position_counts = {}
                
                for i, player_id in enumerate(starters):
                    if player_id:  # Skip None/empty slots
                        player_name = self.get_player_name(player_id)[:15]
                        position, nfl_team = self.get_player_position_team(player_id)
                        last_points, projection = self.get_player_stats(player_id, roster['roster_id'])
                        
                        # Determine display position
                        if i < len(starter_positions):
                            display_pos = starter_positions[i]
                        else:
                            if position not in position_counts:
                                position_counts[position] = 1
                                display_pos = position
                            else:
                                position_counts[position] += 1
                                display_pos = f"{position}{position_counts[position]}"
                        
                        # Special handling for DEF
                        if position == 'DEF':
                            display_pos = 'DST'
                        
                        starter_lines.append(f"{display_pos:<4} :: {player_name:<15} ({nfl_team:>3}) {last_points:>5.1f}")
                        if isinstance(last_points, (int, float)):
                            total_starter_points += last_points
                    else:
                        display_pos = starter_positions[i] if i < len(starter_positions) else "???"
                        starter_lines.append(f"{display_pos:<4} :: {'[Empty]':<15} (---) {0:>5.1f}")
            
            # Prepare bench data (including IR as bench positions)
            bench_lines = []
            bench_players = [p for p in players if p not in starters and p not in taxi]
            
            # Add IR players to bench display
            if reserve:
                bench_players.extend(reserve)
            
            if bench_players:
                bench_by_position = defaultdict(list)
                ir_players = set(reserve) if reserve else set()
                
                for player_id in bench_players:
                    player_name = self.get_player_name(player_id)[:15]
                    position, nfl_team = self.get_player_position_team(player_id)
                    last_points, projection = self.get_player_stats(player_id, roster['roster_id'])
                    
                    # Mark IR players
                    if player_id in ir_players:
                        player_name = f"{player_name} (IR)"
                        player_name = player_name[:15]  # Re-truncate after adding (IR)
                    
                    bench_by_position[position].append((player_name, nfl_team, last_points))
                
                # Display by position
                for pos in ['QB', 'RB', 'WR', 'TE', 'K', 'DEF']:
                    if pos in bench_by_position:
                        players_in_pos = bench_by_position[pos]
                        display_pos = 'DST' if pos == 'DEF' else pos
                        
                        if len(players_in_pos) == 1:
                            name, team, points = players_in_pos[0]
                            bench_lines.append(f"{display_pos:<4} :: {name:<15} ({team:>3}) {points:>5.1f}")
                        else:
                            # Multiple players - put first one with position, others indented
                            name, team, points = players_in_pos[0]
                            bench_lines.append(f"{display_pos:<4} :: {name:<15} ({team:>3}) {points:>5.1f}")
                            for name, team, points in players_in_pos[1:]:
                                bench_lines.append(f"{'':>4}    {name:<15} ({team:>3}) {points:>5.1f}")
                
                # Handle other positions
                for pos, players_in_pos in bench_by_position.items():
                    if pos not in ['QB', 'RB', 'WR', 'TE', 'K', 'DEF']:
                        for name, team, points in players_in_pos:
                            bench_lines.append(f"{pos:<4} :: {name:<15} ({team:>3}) {points:>5.1f}")
            
            # Output side-by-side
            output += f">> STARTING LINEUP :: {team_name.upper()}"
            if bench_lines:
                padding = " " * (47 - len(f">> STARTING LINEUP :: {team_name.upper()}"))
                output += f"{padding}>> BENCH :: {team_name.upper()}\n"
            else:
                output += "\n"
            
            output += "─" * 47
            if bench_lines:
                output += " " + "─" * 31 + "\n"
            else:
                output += "\n"
            
            # Display lines side by side
            max_lines = max(len(starter_lines), len(bench_lines))
            
            for i in range(max_lines):
                # Starter line
                if i < len(starter_lines):
                    starter_line = starter_lines[i]
                else:
                    starter_line = " " * 47
                
                output += starter_line
                
                # Bench line
                if i < len(bench_lines):
                    bench_line = bench_lines[i]
                    # Pad starter line to 47 chars if needed
                    if len(starter_line) < 47:
                        output += " " * (47 - len(starter_line))
                    output += " " + bench_line
                
                output += "\n"
            
            # Bottom separator and team projection
            output += "─" * 47
            if bench_lines:
                output += " " + "─" * 31 + "\n"
            else:
                output += "\n"
            
            output += f"TEAM PROJECTION: {total_starter_points:.1f} pts"
            if bench_lines:
                output += " " * (47 - len(f"TEAM PROJECTION: {total_starter_points:.1f} pts"))
            output += "\n\n"
            
            # TAXI (for dynasty leagues) - full width
            if taxi:
                output += f">> TAXI SQUAD :: {team_name.upper()}\n"
                output += "─" * 47 + "\n"
                
                for player_id in taxi:
                    player_name = self.get_player_name(player_id)[:15]
                    position, nfl_team = self.get_player_position_team(player_id)
                    last_points, projection = self.get_player_stats(player_id, roster['roster_id'])
                    
                    display_pos = 'DST' if position == 'DEF' else position
                    output += f"{display_pos:<4} :: {player_name:<15} ({nfl_team:>3}) {last_points:>5.1f}\n"
                
                output += "─" * 47 + "\n\n"
            
        return output
    
    def create_fun_stats(self):
        """Create fun/nerdy statistics section"""
        leaders = self.get_league_leaders()
        
        output = """
┌─────────────────────────────────────────────────────────────────────────────┐
│                          🤓 NERDY STATS 🤓                                  │
└─────────────────────────────────────────────────────────────────────────────┘

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
    
    def generate_report(self, filename="sleeper_report.txt"):
        """Generate the complete ASCII report"""
        print("🎨 Generating ASCII report...")
        
        report = ""
        report += self.create_ascii_header()
        report += self.create_standings_table()
        report += self.create_leaders_section()
        report += self.create_fun_stats()
        report += self.create_roster_section()
        
        # Footer
        report += f"""

┌─────────────────────────────────────────────────────────────────────────────┐
│                     Generated by sleeper-cli v1.0 🔥                       │
│                        Keep grinding, fantasy legends! 🏆                   │
└─────────────────────────────────────────────────────────────────────────────┘

"""
        
        # Save to file
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(report)
        
        # Also print to console
        print(report)
        print(f"📝 Report saved to: {filename}")

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
        
        # Generate ASCII report
        cli.generate_report()
        
        # Generate HTML report
        cli.generate_html_report()
        
        print("\n🎉 Report generation complete!")
        print("📝 Text version: sleeper_report.txt (best in terminal)")
        print("🌐 HTML version: sleeper_report.html (open in Safari)")
        
    except Exception as e:
        print(f"❌ Error generating report: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
