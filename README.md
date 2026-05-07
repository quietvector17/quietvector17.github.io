# quietvector17.github.io

Static GitHub Pages site for WoW raid tools and strategy notes.

## Live Site

- https://quietvector17.github.io

## Site Pages

- `index.html`: Throne of Thunder Warcraft Logs fight analysis dashboard.
- `soo-strats.html`: Siege of Orgrimmar strategy notes rendered from split Markdown files in `strats/soo/`.

## Fight Analysis

The ToT dashboard generates breakdowns from Warcraft Logs reports. Users provide their own WCL client credentials in-browser.

- Overall: kill durations, wipes before kills, player deaths, lust timing
- Council of Elders: elder death order/times
- Megaera: head death order and inferred final head
- Iron Qon: dog death timing + windstorm markers
- Lei Shen: intermission timing via Supercharge Conduits
- Tortos: Shell Concussion applications + uptime

## Usage

1. Open the live site.
2. Paste a Warcraft Logs report URL or code.
3. Enter your WCL Client ID and Client Secret.
4. Click **Generate Analysis**.

## WCL Credentials

Create a Warcraft Logs API client at:
https://www.warcraftlogs.com/api/clients

Your credentials are used only in your browser session and are not stored.

## Local Development

Just open `index.html` in a browser or serve the folder with a static server.

The SoO strategy page fetches Markdown files at runtime, so it should be served over HTTP rather than opened directly from disk.

## Notes

- The Python scripts in `scripts/` are local Warcraft Logs analysis helpers.
- Client credentials are read from environment variables for local script runs:
  - `WCL_CLIENT_ID`
  - `WCL_CLIENT_SECRET`
