# Shared project workflow

For a request to continue or change the shared project:

1. Call get_project_state and list_project_files first.
2. Read the relevant instructions and only the source sections needed for the request.
3. Do not ask for files that are already in shared_files.
4. Before replacing an existing file, read it. Use overwrite only for an intentional full replacement; the previous version is backed up.
5. After saving code changes, call update_project_state with a short summary, current issue, and exact next step.
6. Keep handoffs concise. Do not claim a test or preview was run unless it actually was.

The server handles UTF-8 text files only and does not provide access to binary assets.
