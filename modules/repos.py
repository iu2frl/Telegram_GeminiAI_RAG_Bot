
import logging
import os
import shutil
import time

import git

from modules import state


def clone_or_pull_repo():
    """Clones the repository if it doesn't exist, otherwise pulls the latest changes."""
    logging.info("Cloning or pulling repository from [%s] to [%s]...", state.REPO_URL, state.LOCAL_REPO_PATH)

    try:
        logging.info("Starting repository update...")

        if not os.path.exists(f"{state.LOCAL_REPO_PATH}/.git"):
            try:
                # Delete all files in the local repository path
                if os.path.exists(state.LOCAL_REPO_PATH):
                    logging.debug("Deleting existing files in [%s]", state.LOCAL_REPO_PATH)
                    shutil.rmtree(state.LOCAL_REPO_PATH)
                logging.debug("Cloning repository at [%s]...", state.REPO_URL)
                git.Repo.clone_from(state.REPO_URL, state.LOCAL_REPO_PATH)
            except Exception as e:
                logging.critical("Failed to clone repository: %s", e)
                raise
        else:
            try:
                logging.debug("Pulling latest changes from repository...")
                repo = git.Repo(state.LOCAL_REPO_PATH)
                repo.remotes.origin.pull()
            except Exception as e:
                if "128" in str(e):
                    logging.warning("Repository pull failed due to authentication error, retrying clone...")
                    shutil.rmtree(state.LOCAL_REPO_PATH)
                    git.Repo.clone_from(state.REPO_URL, state.LOCAL_REPO_PATH)
                else:
                    logging.critical("Failed to pull latest changes: %s", e)
                    raise

        logging.info("Repository update completed.")

    except Exception as e:
        logging.error("Failed to update source files: %s", e)


def list_files_in_folder(folder_path):
    """
    Returns a list of all markdown files in the given folder and its subdirectories.

    Args:
        folder_path (str): Path to the folder.

    Returns:
        list: List of file paths in the folder and its subdirectories.
    """
    if not os.path.isdir(folder_path):
        raise ValueError(f"The provided path [{folder_path}] is not a directory.")

    files_list = []
    for root, _, files in os.walk(folder_path):
        for file in files:
            if file.lower().endswith(".md"):
                files_list.append(os.path.join(root, file))

    logging.debug("Found %i markdown files in folder [%s]", len(files_list), folder_path)
    return files_list


def pull_and_update():
    """Pulls the latest changes from the repository and updates the Gemini AI"""

    while state.RELOADING_GEMINI:
        logging.info("Gemini API is being reloaded, waiting for it to complete...")
        time.sleep(1)

    try:
        clone_or_pull_repo()
        state.RELOADING_GEMINI = True
        from modules.gemini import gemini_initialize
        gemini_initialize()
    except Exception as e:
        logging.critical("Failed to update the repository and reload Gemini AI: %s", e)
    finally:
        state.RELOADING_GEMINI = False

