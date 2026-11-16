# MCP Shared Workspace

A small, self-hosted Model Context Protocol (MCP) server for sharing project progress and UTF-8 text files between your own AI accounts.

The server stores everything on your computer. It does not call an AI API and does not require an API key. Your AI provider may still apply its normal account, subscription, connector, or usage limits.

## What it provides

- Read and update a shared project status.
- List, search, and read files in a local shared_files folder.
- Read a bounded section of a file to reduce unnecessary context.
- Make guarded text patches using a file hash and expected match count.
- Write a new text file or replace an existing one with a local backup.

Files written by the server are UTF-8 text files up to 500 KB. It does not edit binary assets.

## Quick setup on Windows

1. Install Python 3.10 or newer, Tailscale, and Git.
2. Download this repository from GitHub or clone it.
3. Open PowerShell in the downloaded folder and run:

       Set-ExecutionPolicy -Scope Process Bypass
       .\start_local.ps1

   The first run creates a local Python environment and installs the MCP dependency.

4. Put project files in shared_files. The server keeps status in data/state.json. The starter instructions at shared_files/WORKFLOW.md are versioned; your other project files are excluded from Git.
5. For local MCP clients, configure the client to launch the Python executable in .venv/Scripts/python.exe with server.py as its argument.

## Connect Claude accounts through Tailscale Funnel

Use this when the MCP server should be reachable by Claude's website from multiple accounts. The computer owner signs into their own Tailscale account; each Claude account connects to the owner's server URL.

1. Sign in to Tailscale on this computer and enable Funnel for this device when Tailscale asks.
2. Run PowerShell as Administrator in this repository folder.
3. Start the server and Funnel for this session:

       Set-ExecutionPolicy -Scope Process Bypass
       .\start_tailscale_mcp.ps1

4. Copy the HTTPS hostname and the private MCP path printed in the PowerShell window. The complete URL is the hostname followed by that path.
5. In each supported Claude account, add the same complete URL under Settings -> Connectors -> Add custom connector. Enable the connector in each chat where you want to use it.

The hostname is tied to the owner's Tailscale device and tailnet. Keep this PowerShell window and computer on while using the connector. Press Ctrl+C to stop it. The next time you start it, the hostname and generated private path stay the same unless you change the device/tailnet or delete .mcp-secret.

## Important access warning

The random path is the server's access secret. Anyone who gets the complete connector URL can read and change the shared status and files. Share it only with people you trust to have full read and write access. Do not publish it, paste it in issues, or commit it.

Never put passwords, API keys, personal account information, or private project files in the public Git repository. This repository contains only the reusable server and setup instructions. The data folder, your private files in shared_files, virtual environment, and .mcp-secret are ignored by Git; only the generic starter workflow in shared_files is tracked.

This setup has no hosted server cost, but it depends on your computer, internet connection, Tailscale availability, and the current limits/terms of the AI and tunnel providers. It does not transfer chat history or bypass provider usage limits; it shares only the data saved through this MCP server.

## Publish your own public copy

1. On GitHub, create a new repository named mcp-shared-workspace and choose Public. Leave the options to add a README, .gitignore, or license unchecked because this folder already has them.
2. Open PowerShell in this folder and run these commands. Replace YOUR_USERNAME with your GitHub username:

       git init
       git add .
       git status --short
       git commit -m "Initial public template"
       git branch -M main
       git remote add origin https://github.com/YOUR_USERNAME/mcp-shared-workspace.git
       git push -u origin main

Review the git status output before committing. It should contain only the reusable server, scripts, docs, license, and generic starter workflow. Do not use git add -f for ignored files.
## Repository layout

- server.py: MCP tools and local JSON/text persistence.
- start_local.ps1: starts the local stdio server.
- start_tailscale_mcp.ps1: starts the HTTP server and Tailscale Funnel on demand.
- data/: local project state; excluded from Git.
- shared_files/WORKFLOW.md: generic starter instructions available through MCP. Other files placed in shared_files/ are excluded from Git.
- WORKFLOW.md: maintainer note explaining the MCP-visible workflow location.
- .mcp-secret: generated URL path secret; excluded from Git.
