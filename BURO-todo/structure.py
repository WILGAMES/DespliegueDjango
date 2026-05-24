import os

def list_files(start_path):
    # Folders to ignore
    exclude = {'.git', 'venv', '__pycache__', '.idea', '.vscode', 'static', 'media'}
    
    for root, dirs, files in os.walk(start_path):
        # Modify dirs in-place to skip excluded folders
        dirs[:] = [d for d in dirs if d not in exclude]
        
        level = root.replace(start_path, '').count(os.sep)
        indent = ' ' * 4 * (level)
        print(f'{indent}{os.path.basename(root)}/')
        sub_indent = ' ' * 4 * (level + 1)
        for f in files:
            print(f'{sub_indent}{f}')

# Run it on the current directory
list_files('.')
