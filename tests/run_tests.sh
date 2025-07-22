#!/bin/bash
# A comprehensive test script for the AutoML TodoList CLI tool.

# Stop on first error
set -e

echo "--- 1. SETUP: Ensuring a clean environment ---"
rm -f tasks.db
todo init
echo ""

echo "--- 2. CORE WORKFLOW: Testing the full lifecycle of a task ---"
echo "--> Adding a new task to the 'Default Season'..."
todo add "My first real task" -p "Core Test" -d 3 --dow 1

echo "--> Current active task list:"
todo list
echo ""

echo "--> Starting task 1..."
todo start 1
echo "--> List after starting task:"
todo list
echo ""

echo "--> Marking task 1 as done..."
todo done 1
echo "--> Active list should now be empty:"
todo list
echo ""

echo "--> Checking the log for the completed task (no LP yet):"
todo log
echo ""

echo "--> Updating completed task 1 with reflection and final difficulty..."
todo update 1 -d 5 -r 'This was harder than expected!'
echo "--> Log after update (should have LP Gain):"
todo log
echo ""

echo "--- 3. AFTER-THE-FACT LOGGING: Testing the --completed flag ---"
echo "--> Adding a pre-completed task for Sunday (DoW 0)..."
todo add "Logged this after it was done" -p "Logging Test" -d 1 --dow 0 --completed
echo "--> Log after adding the completed task:"
todo log
echo ""

echo "--- 4. SEASON MANAGEMENT: Testing archiving and switching ---"
echo "--> Starting a new season..."
todo season start "Test Season 2"
echo ""

echo "--> Active list in new season should be empty:"
todo list
echo "--> Log in new season should be empty:"
todo log
echo ""

echo "--> Adding a task to 'Test Season 2'..."
todo add "A task in the second season" -p "Season Test"
echo "--> Active list in 'Test Season 2':"
todo list
echo ""

echo "--> Switching back to the 'Default Season' (ID 1)..."
todo season switch 1
echo ""

echo "--> Log for 'Default Season' should show our original tasks:"
todo log
echo ""

echo "--- 5. FINAL STATUS CHECK: Verifying LP calculation ---"
echo "--> Checking status for the 'Default Season':"
todo status
echo ""

echo "--- ALL TESTS COMPLETED ---" 