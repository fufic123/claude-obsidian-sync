#!/bin/bash
cd "$(dirname "$0")"
/usr/bin/python3 main.py >> service.log 2>&1
