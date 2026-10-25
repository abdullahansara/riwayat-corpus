"""Read-only consistency audit of hadith_master.db.  Usage: python tools/audit_db.py [path/to/hadith_master.db]
Prints one line per check: count of offending rows (0 = clean) and a few examples."""
import sqlite3, sys, os, pathlib, re, time
db = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), '..', 'data', 'HadithMaster', 'hadith_master.db')
c = sqlite3.connect('file:%s?mode=ro' % pathlib.Path(db).resolve().as_posix(), uri=True)
t0 = time.time()
BUDGET = int(os.environ.get('CHECK_SECONDS', 180))
def chk(name, sql, show=3):
    start = time.time(); c.set_progress_handler(lambda: 1 if time.time() - start > BUDGET else 0, 100000)
    try:
        rows = c.execute(sql).fetchall()
    except Exception as e:
        print(f'[SKIP] {name}: {str(e)[:60]} after {time.time()-start:.0f}s', flush=True); return
    finally:
        c.set_progress_handler(None, 0)
    n = rows[0][0] if len(rows) == 1 and len(rows[0]) == 1 and isinstance(rows[0][0], int) else len(rows)
    print(f'[{n:>9,}] {name}   ({time.time()-t0:.0f}s)', flush=True)
    if not (len(rows) == 1 and len(rows[0]) == 1):
        for r in rows[:show]: print('            ', tuple(str(x)[:70] for x in r), flush=True)

# referential integrity
chk('mentions pointing to missing narrator', 'select count(*) from chain_mention m left join narrator n on n.id=m.narrator_id where m.narrator_id is not null and n.id is null')
chk('mentions pointing to missing hadith', 'select count(*) from chain_mention m left join hadith h on h.id=m.hadith_id where h.id is null')
chk('edges with missing narrator', 'select count(*) from narrator_edge e left join narrator a on a.id=e.student left join narrator b on b.id=e.teacher where a.id is null or b.id is null')
chk('narrator_name rows with missing narrator', 'select count(*) from narrator_name x left join narrator n on n.id=x.narrator_id where n.id is null')
chk('source ids with missing narrator', 'select count(*) from narrator_source_id x left join narrator n on n.id=x.narrator_id where n.id is null')
chk('reference_chain ids not in narrator (rows)', "select count(*) from reference_chain r where exists (select 1 from json_each(r.narrator_ids) j left join narrator n on n.id=j.value where n.id is null)")
# hadith-level
chk('hadith n_narrators != mention count', "select count(*) from hadith h join (select hadith_id, count(*) c from chain_mention group by hadith_id) m on m.hadith_id=h.id where h.n_narrators != m.c")
chk('hadith with chain_tier!=none but no mentions', "select count(*) from hadith h where chain_tier!='none' and not exists (select 1 from chain_mention m where m.hadith_id=h.id)")
chk('hadith with chain_tier=none but mentions', "select count(*) from hadith h where chain_tier='none' and exists (select 1 from chain_mention m where m.hadith_id=h.id)")
chk('matn_start/end outside text', 'select count(*) from hadith where matn_start<0 or matn_end>length(text) or matn_start>matn_end')
chk('hadith text shorter than 20 chars', 'select count(*) from hadith where length(text)<20', 5)
chk('hadith text longer than 20000 chars', 'select count(*) from hadith where length(text)>20000')
chk('hadith text with Latin letters >30%', "select count(*) from hadith where length(text)>0 and (length(text)-length(replace(replace(replace(lower(text),'a',''),'e',''),'o','')))*1.0/length(text)>0.1")
chk('hadith text_tagged missing for chain hadith', "select count(*) from hadith where chain_tier!='none' and (text_tagged is null or text_tagged='')")
chk('identical text in >1 hadith (distinct texts, first 200 chars + length)', 'select count(*) from (select substr(text,1,200) t, length(text) l from hadith group by 1,2 having count(*)>1)')
chk('identical text in >1 hadith (extra copies)', 'select coalesce(sum(c-1),0) from (select count(*) c from hadith group by substr(text,1,200), length(text) having c>1)')
# mention-level
chk('mentions with empty surface', "select count(*) from chain_mention where surface is null or trim(surface)=''")
chk('mentions with start>=end', 'select count(*) from chain_mention where start>=end')
chk('mentions positions not 1..n contiguous (hadith)', 'select count(*) from (select hadith_id from chain_mention group by hadith_id having max(pos)-min(pos)+1!=count(*))')
chk('same narrator twice in one chain', 'select count(*) from (select hadith_id, narrator_id from chain_mention where narrator_id is not null group by 1,2 having count(*)>1)')
chk('same narrator adjacent in chain', 'select count(*) from chain_mention a join chain_mention b on a.hadith_id=b.hadith_id and b.pos=a.pos+1 and a.narrator_id=b.narrator_id where a.narrator_id is not null')
chk('surface is a transmission verb/filler', "select count(*) from chain_mention where trim(surface) in ('قال','عن','حدثنا','أخبرنا','حدثني','أخبرني','ثنا','أنا','نا','أن','أنه','أنها','وقال','قالت','سمعت','يقول')")
chk('surface is a filler: top examples', "select surface, count(*) from chain_mention where trim(surface) in ('قال','عن','حدثنا','أخبرنا','حدثني','أخبرني','ثنا','أنا','نا','أن','أنه','وقال','قالت','سمعت','يقول') group by 1 order by 2 desc", 8)
chk('mentions: 1-word surface assigned id by name lookup', "select count(*) from chain_mention where narrator_id is not null and instr(trim(surface),' ')=0 and id_method like 'name_lookup%'")
chk('mentions: id_method distribution', 'select id_method, count(*) from chain_mention group by 1 order by 2 desc', 20)
chk('mentions with low confidence (<0.7)', 'select count(*) from chain_mention where narrator_id is not null and id_confidence<0.7')
chk('mentions: same surface -> >1 narrator within one hadith', 'select count(*) from (select hadith_id, surface from chain_mention where narrator_id is not null group by 1,2 having count(distinct narrator_id)>1)')
# narrator-level
chk('narrators with no mentions, no edges, no source ids', 'select count(*) from narrator n where not exists (select 1 from chain_mention m where m.narrator_id=n.id) and not exists (select 1 from narrator_edge e where e.student=n.id or e.teacher=n.id)')
chk('narrators with no mentions at all', 'select count(*) from narrator n where not exists (select 1 from chain_mention m where m.narrator_id=n.id)')
chk('narrators with empty std_name', "select count(*) from narrator where std_name is null or trim(std_name)=''")
chk('narrators with 1-token std_name', "select count(*) from narrator where instr(trim(std_name),' ')=0")
chk('narrators std_name contains digits/Latin', "select count(*) from narrator where std_name glob '*[0-9A-Za-z]*'", 5)
chk('narrators with ≥2 narrators sharing exact std_name', 'select count(*) from (select std_name from narrator group by std_name having count(*)>1)')
chk('narrators sharing exact std_name (extra rows)', 'select coalesce(sum(c-1),0) from (select count(*) c from narrator group by std_name having c>1)')
chk('narrators sharing std_name+death_year', 'select count(*) from (select std_name,death_year from narrator where death_year is not null group by 1,2 having count(*)>1)', 5)
chk('death_year implausible (<0 or >1500)', 'select count(*) from narrator where death_year<0 or death_year>1500')
chk('birth_year > death_year', 'select count(*) from narrator where birth_year is not null and death_year is not null and birth_year>death_year')
chk('death_year distribution by century', "select (death_year/100)*100, count(*) from narrator where death_year is not null group by 1 order by 1", 25)
chk('narrator tradition values', 'select tradition, count(*) from narrator group by 1')
chk('shia narrator used in sunni hadith', "select count(*) from chain_mention m join hadith h on h.id=m.hadith_id join narrator n on n.id=m.narrator_id where h.tradition='sunni' and n.tradition like 'shi%'")
chk('sunni narrator used in shia hadith', "select count(*) from chain_mention m join hadith h on h.id=m.hadith_id join narrator n on n.id=m.narrator_id where h.tradition like 'shi%' and n.tradition like 'sunni%'")
chk('narrator.n_sources != distinct sources in narrator_source_id', 'select count(*) from narrator n where n_sources != (select count(distinct source) from narrator_source_id s where s.narrator_id=n.id)')
# names
chk('name forms (norm) mapping to >5 narrators', 'select count(*) from (select norm from narrator_name where norm is not null group by norm having count(distinct narrator_id)>5)')
chk('top ambiguous name forms', 'select norm, count(distinct narrator_id) c from narrator_name where norm is not null group by norm order by c desc', 8)
chk('empty norm forms', "select count(*) from narrator_name where norm is null or trim(norm)=''")
# edges / graph
chk('edge self-loops', 'select count(*) from narrator_edge where student=teacher')
chk('2-cycles (A teaches B and B teaches A)', 'select count(*) from narrator_edge a join narrator_edge b on a.student=b.teacher and a.teacher=b.student where a.student<a.teacher')
chk('2-cycles with both n_hadith>=3', 'select count(*) from narrator_edge a join narrator_edge b on a.student=b.teacher and a.teacher=b.student where a.student<a.teacher and a.n_hadith>=3 and b.n_hadith>=3')
chk('teacher died >=30y after student (n_hadith>=1)', 'select count(*) from narrator_edge e join narrator s on s.id=e.student join narrator t on t.id=e.teacher where s.death_year is not null and t.death_year is not null and t.death_year-s.death_year>=30')
chk('teacher died >=30y after student: examples', 'select e.student, e.teacher, s.death_year, t.death_year, e.n_hadith from narrator_edge e join narrator s on s.id=e.student join narrator t on t.id=e.teacher where s.death_year is not null and t.death_year is not null and t.death_year-s.death_year>=30 order by e.n_hadith desc', 5)
chk('edge n_hadith=1 share', 'select count(*) from narrator_edge where n_hadith=1')
