"""Aislamiento de metadatos de la entrega; no requiere una conexión real."""
import unittest
from sqlalchemy import Enum, create_mock_engine, create_engine, text, select, insert, func
from app.db.session import Base
from app.models import models
from app.db.presentation_snapshot import isolated_metadata, copy_selection, SCHEMA


class PresentationMetadataTests(unittest.TestCase):
    def test_all_references_and_enum_types_use_the_presentation_schema(self):
        target=isolated_metadata(Base.metadata)
        self.assertEqual(len(target.tables),len(Base.metadata.tables))
        for table in target.sorted_tables:
            self.assertEqual(table.schema,SCHEMA)
            for fk in table.foreign_keys:self.assertEqual(fk.column.table.schema,SCHEMA)
            for col in table.c:
                if isinstance(col.type,Enum):
                    self.assertEqual(col.type.schema,SCHEMA)
                    self.assertIsNot(col.type,Base.metadata.tables[table.name].c[col.name].type)
        self.assertTrue(all(table.schema is None for table in Base.metadata.tables.values()))

    def test_generated_ddl_does_not_create_objects_in_source_or_public(self):
        statements=[]
        engine=create_mock_engine('postgresql://',lambda sql,*args,**kwargs:statements.append(str(sql.compile(dialect=engine.dialect))))
        isolated_metadata(Base.metadata).create_all(engine,checkfirst=False)
        self.assertTrue(any('CREATE TYPE '+SCHEMA+'.' in sql for sql in statements))
        self.assertTrue(any('CREATE TABLE '+SCHEMA+'.users' in sql for sql in statements))
        self.assertFalse(any('CREATE TABLE ssp_test.' in sql or 'CREATE TYPE ssp_test.' in sql or 'CREATE TABLE public.' in sql for sql in statements))

    def test_copy_excludes_non_demo_accounts_and_dependent_rows(self):
        engine=create_engine('sqlite://')
        target=isolated_metadata(Base.metadata)
        with engine.begin() as conn:
            conn.execute(text(f"ATTACH DATABASE ':memory:' AS {SCHEMA}"))
            Base.metadata.create_all(conn);target.create_all(conn)
            conn.execute(models.User.__table__.insert(),[{'id':key,'nombres':key,'apellidos':'Test','email':key+'@example.org','role':'ALUMNO','hashed_password':'unused'} for key in ['safe','excluded']])
            conn.execute(models.Aula.__table__.insert(),[{'id':key,'nombre':key,'codigo':key,'periodo':'TEST','profesor_id':owner} for key,owner in [('a','safe'),('b','excluded')]])
            conn.execute(models.Inscripcion.__table__.insert(),[{'id':key,'aula_id':'a','alumno_id':owner} for key,owner in [('one','safe'),('two','excluded')]])
            for original in [models.User.__table__,models.Aula.__table__,models.Inscripcion.__table__]:
                dest=target.tables[f'{SCHEMA}.{original.name}']
                conn.execute(insert(dest).from_select([col.name for col in dest.c],copy_selection(original,dest,target,{'safe'})))
            self.assertEqual(conn.execute(select(func.count()).select_from(target.tables[f'{SCHEMA}.users'])).scalar_one(),1)
            self.assertEqual(conn.execute(select(func.count()).select_from(target.tables[f'{SCHEMA}.aulas'])).scalar_one(),1)
            self.assertEqual(conn.execute(select(func.count()).select_from(target.tables[f'{SCHEMA}.inscripciones'])).scalar_one(),1)
            self.assertEqual(conn.execute(select(func.count()).select_from(models.User.__table__)).scalar_one(),2)
        engine.dispose()


if __name__=='__main__':unittest.main()
