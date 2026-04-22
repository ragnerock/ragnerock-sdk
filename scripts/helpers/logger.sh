#!/bin/bash
# This is a convenience script to allow for better formatted bash log messages
# This should _NOT_ be run as a standalone script and instead should be sourced in

# ======== COLORS ======== #

RED='\033[0;31m'
YELLOW='\033[0;33m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
BLUE='\033[0;34m'
NO_COLOR='\033[0m'

# ======== LOGGING ======== #

# Set log level to INFO if it doesn't exist
if [[ -z "${LOG_LEVEL}" ]]; then
  export LOG_LEVEL="INFO"
fi

# Setup variable for log level comparison
function _set_log_level {
    case ${LOG_LEVEL} in
        FATAL)
            export LOG_LEVEL_INT=0
            ;;
        SUCCESS)
            export LOG_LEVEL_INT=1
            ;;
        ERROR)
            export LOG_LEVEL_INT=2
            ;;
        WARN)
            export LOG_LEVEL_INT=3
            ;;
        INFO)
            export LOG_LEVEL_INT=4
            ;;
        DEBUG)
            export LOG_LEVEL_INT=5
            ;;
        TRACE)
            export LOG_LEVEL_INT=6
            ;;
        *)
            echo "[${YELLOW}WARN${NO_COLOR}] :: Invalid log level '${LOG_LEVEL}' -- setting level to 'INFO'"
            export LOG_LEVEL='INFO'
            export LOG_LEVEL_INT=4
            ;;
    esac
}

# Print out log statement depending on level
function _log {
    LEVEL=$1
    MESSAGE=$2
    case ${LEVEL} in
        FATAL)
            if [[ ${LOG_LEVEL_INT} -ge 0 ]]; then
                echo -e "[${RED}FATAL${NO_COLOR}] :: ${MESSAGE}"
                exit 1
            fi
            ;;
        SUCCESS)
            if [[ ${LOG_LEVEL_INT} -ge 1 ]]; then
                echo -e "[${GREEN}SUCCESS${NO_COLOR}] :: ${MESSAGE}"
            fi
            ;;
        ERROR)
            if [[ ${LOG_LEVEL_INT} -ge 2 ]]; then
                echo -e "[${RED}ERROR${NO_COLOR}] :: ${MESSAGE}"
            fi
            ;;
        WARN)
            if [[ ${LOG_LEVEL_INT} -ge 3 ]]; then
                echo -e "[${YELLOW}WARN${NO_COLOR}] :: ${MESSAGE}"
            fi
            ;;
        INFO)
            if [[ ${LOG_LEVEL_INT} -ge 4 ]]; then
                echo -e "[${GREEN}INFO${NO_COLOR}] :: ${MESSAGE}"
            fi
            ;;
        DEBUG)
            if [[ ${LOG_LEVEL_INT} -ge 5 ]]; then
                echo -e "[${CYAN}DEBUG${NO_COLOR}] :: ${MESSAGE}"
            fi
            ;;
        TRACE)
            if [[ ${LOG_LEVEL_INT} -ge 6 ]]; then
                echo -e "[${BLUE}TRACE${NO_COLOR}] :: ${MESSAGE}"
            fi
            ;;
        *)
            echo "Invalid log level: ${LEVEL}"
    esac
}

_set_log_level