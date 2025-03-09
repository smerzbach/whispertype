#!/bin/bash

# Unset problematic environment variables
unset PYTHONPATH
unset PYTHONHOME

# Execute the provided command with clean environment
"$@" 