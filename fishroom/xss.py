#coding=utf-8
import re
import html 

def md_escape(text):
    replacements = [
        [r'\*', r'\\*'],
        [r'#', r'\\#'],
        [r'\/', r'\\/'],
        [r'\(', r'\\('],
        [r'\)', r'\\)'],
        [r'\[', r'\\['],
        [r'\]', r'\\]'],
        [r'\<', r'&lt;'],
        [r'\>', r'&gt;'],
        [r'_', r'\\_'],
        [r'`', r'\\`'],
    ]
    return replace(text,replacements)

def replace(text,rs):
    for r in rs:
        text = re.sub(r[0],r[1],text)
    return text

def cooked_unescape(message):
    return html.unescape(re.sub(r'<[^>]+>','', message))
