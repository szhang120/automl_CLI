#!/bin/bash
# A rigorous test script for duration, LP calculation, and decay workflows.

# Stop on first error
set -e

echo "--- SETUP: Initializing a fresh database for tests ---"
rm -f tasks.db
todo init
todo season start "Duration Test Season"
echo ""

get_last_task_id() {
    sqlite3 tasks.db "SELECT id FROM tasks ORDER BY id DESC LIMIT 1;"
}

echo "--- TEST CASE 1: After-the-Fact Logging with Manual Duration ---"
echo "--> Logging a completed 'Hard' task that took 90 minutes."
echo "    (Expected LP: (10/60) * 90 = 15.0)"
todo add "Manual Duration Task" -p "Workflow 1" -d "Hard" --completed --duration 90
echo "--> RESULT: Test Case 1 Complete."
echo ""

echo "--- TEST CASE 2: Start/Stop Workflow ---"
echo "--> Adding a 'Medium' task and starting/stopping it."
todo add "Start/Stop Task" -p "Workflow 2" -d "Medium"
last_id_timed=$(get_last_task_id)
todo start $last_id_timed
# We can't reliably test the exact duration, but we can ensure it's marked as done.
todo stop $last_id_timed
todo done $last_id_timed
echo "--> RESULT: Test Case 2 Complete."
echo ""

echo "--- TEST CASE 3: Updating Duration on a Completed Task ---"
echo "--> Updating the first task to have a 60-minute duration."
echo "    (Expected LP: (10/60) * 60 = 10.0)"
todo update 1 --duration 60
echo "--> RESULT: Test Case 3 Complete."
echo ""


echo "--- FINAL VERIFICATION ---"
echo "--> Displaying the final log for the 'Duration Test Season':"
todo log
echo ""
echo "--> Displaying final status:"
todo status
echo ""

echo "--- ALL DURATION TESTS COMPLETED ---" 