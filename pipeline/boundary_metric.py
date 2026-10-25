"""Boundary metric agreed with the user: a leading connector (قال, أن, يقول, honorifics ...) in or out of the matn is fine.
start_ok: the text between the DB start and the label start holds only connector words.  end_ok: same for the end (plus <= 10 chars).
leak: a chain mention overlaps the matn, or a chain verb (حدثنا, أخبرنا ...) occurs in the matn's first 60 chars."""
import re
from labels_lib import plain
CONN = set('قال قالت قالا قالوا يقول تقول يقولون ان انه انها انهم انا اني انني و ف ثم عن النبي رسول الله صلي عليه وسلم ص رضي عنه عنها عنهما وعلي واله عز وجل قوله يعني اي ا يا'.split())
CHAINV = re.compile(r'(^| )(حدثنا|حدثني|اخبرنا|اخبرني|انبانا|انبا|سمعت|ثنا|نا|اخبره|حدثه)( |$)')
def conn_only(text, a, b):
    if a > b: a, b = b, a
    w = plain(text[a:b])[0].split()
    return all(x in CONN for x in w)
def start_ok(text, db, lab): return abs(db - lab) <= 3 or conn_only(text, db, lab)
def end_ok(text, db, lab): return abs(db - lab) <= 10 or conn_only(text, db, lab)
