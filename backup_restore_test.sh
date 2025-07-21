#!/bin/bash
# An end-to-end test script for the backup and restore functionality.

# Stop on first error
set -e

# --- PHASE 1: Create Initial Data and Export ---
echo "--- PHASE 1: Creating and exporting initial data ---"
rm -f tasks.db backup.json
todo init
todo season start "Original Season"

echo "--> Adding initial tasks..."
todo add "Task 1" -d "Easy" --completed --duration 30
todo add "Task 2" -d "Hard" --completed --duration 120

echo "--> Exporting data to backup.json..."
todo backup export backup.json
echo ""


# --- PHASE 2: Simulate Schema Change and Restore ---
echo "--- PHASE 2: Simulating a schema change and restoring data ---"
echo "--> Deleting the database to simulate a fresh install with a new schema..."
rm -f tasks.db

echo "--> Importing data from backup.json (this will re-create the DB)..."
# The --yes flag auto-confirms the destructive operation prompt.
todo backup import backup.json --yes
echo ""


# --- PHASE 3: Verification ---
echo "--- PHASE 3: Verifying the restored data ---"
echo "--> Displaying the log for the restored data:"
todo log
echo ""

echo "--> Displaying the status for the restored data:"
todo status
echo ""

echo "--- BACKUP AND RESTORE TEST COMPLETED ---" 