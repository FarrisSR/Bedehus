# Project Overview

This repository controls heating for a bedehus (church hall) based on Google Calendar bookings. It checks upcoming events within a configurable time window and switches heating on/off accordingly.

## What It Does
- Reads two Google Calendar IDs: one for Storsalen and one for Bønnerom (prayer room).
- If events exist in the lookahead window, it enables heating; otherwise it disables heating.
- Controls an SR201 relay to switch heating power for Storsalen.
- Updates Glamox room temperature for Storsalen when configured.
- Updates a Mill heater controller for Bønnerom when configured.
- Logs actions to console, file, and/or syslog.

## Main Implementations
- `go-bedehus`: Go implementation that uses `config/config.json`, stores relay state in SQLite, and integrates Google Calendar, SR201, Glamox, and Mill via internal packages.
- `main.py`: Python implementation with hard-coded defaults, relay state stored in `relay_state.txt`, and similar device integrations.

## Key Inputs
- Google service account key file and scopes for Calendar API.
- Device endpoints for SR201, Mill controller, and Glamox API credentials (`secrets.json`).
- Logging configuration (`logging.config`) and runtime config (`config/config.json`).

## Expected Outcome
The system keeps rooms warm ahead of scheduled events while avoiding unnecessary heating when there are no upcoming bookings.
