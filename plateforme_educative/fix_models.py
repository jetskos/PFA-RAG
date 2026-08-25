import os
import glob
files = glob.glob('d:/stage-lms/plateforme_educative/tuteur_ia/**/*.py', recursive=True)
for f in files:
    with open(f, 'r', encoding='utf-8') as file:
        content = file.read()
    if 'llama-3.1-8b-instant' in content:
        content = content.replace(', model_name="llama-3.1-8b-instant"', '')
        content = content.replace('model_name="llama-3.1-8b-instant", ', '')
        content = content.replace('model_name="llama-3.1-8b-instant"', '')
        with open(f, 'w', encoding='utf-8') as file:
            file.write(content)
        print("Updated", f)
