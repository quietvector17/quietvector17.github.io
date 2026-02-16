# Throne of Thunder Fight Analysis

Static GitHub Pages site that generates Throne of Thunder fight breakdowns from a Warcraft Logs report. Users provide their own WCL client credentials in-browser.

## Live Site

- https://quietvector17.github.io

## What It Does

- Overall: kill durations, wipes before kills, player deaths, lust timing
- Council of Elders: elder death order/times
- Megaera: head death order and inferred final head
- Iron Qon: dog death timing + windstorm markers
- Lei Shen: intermission timing via Supercharge Conduits
- Tortos: Shell Concussion applications + uptime

## Usage

1. Open the site.
2. Paste a Warcraft Logs report URL or code.
3. Enter your WCL Client ID and Client Secret.
4. Click **Generate Analysis**.

## WCL Credentials

Create a Warcraft Logs API client at:
https://www.warcraftlogs.com/api/clients

Your credentials are used only in your browser session and are not stored.

## Local Development

Just open `index.html` in a browser or serve the folder with a static server.

## Notes

- The Python scripts in this repo are the original analysis sources.
- Client credentials are read from environment variables for local script runs:
  - `WCL_CLIENT_ID`
  - `WCL_CLIENT_SECRET`
