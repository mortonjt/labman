# ----------------------------------------------------------------------------
# Copyright (c) 2017-, labman development team.
#
# Distributed under the terms of the Modified BSD License.
#
# The full license is in the file LICENSE, distributed with this software.
# ----------------------------------------------------------------------------

from . import base
from . import sql_connection
from . import process
from . import container as container_mod
from . import exceptions as exceptions_mod


class Composition(base.LabmanObject):
    """Composition object

    Attributes
    ----------
    id
    upstream_process
    container
    total_volume
    notes
    """
    @staticmethod
    def factory(composition_id):
        """Initializes the correct composition subclass

        Parameters
        ----------
        composition_id : int
            The composition id

        Returns
        -------
        An instance of a subclass of Composition
        """
        factory_classes = {
            'reagent': ReagentComposition,
            'primer set': PrimerSetComposition,
            'primer': PrimerComposition,
            'sample': SampleComposition,
            'gDNA': GDNAComposition,
            '16S library prep': LibraryPrep16SComposition,
            'normalized gDNA': NormalizedGDNAComposition,
            'shotgun library prep': LibraryPrepShotgunComposition,
            'pool': PoolComposition}

        with sql_connection.TRN as TRN:
            sql = """SELECT description
                     FROM qiita.composition_type
                        JOIN qiita.composition USING (composition_type_id)
                     WHERE composition_id = %s"""
            TRN.add(sql, [composition_id])
            c_type = TRN.execute_fetchlast()
            constructor = factory_classes[c_type]

            sql = """SELECT {}
                     FROM {}
                     WHERE composition_id = %s""".format(
                        constructor._id_column, constructor._table)
            TRN.add(sql, [composition_id])
            subclass_id = TRN.execute_fetchlast()
            instance = constructor(subclass_id)

        return instance

    @classmethod
    def _common_creation_steps(cls, process, container, volume):
        """"""
        with sql_connection.TRN as TRN:
            sql = """SELECT composition_type_id
                     FROM qiita.composition_type
                     WHERE description = %s"""
            TRN.add(sql, [cls._composition_type])
            ct_id = TRN.execute_fetchlast()

            sql = """INSERT INTO qiita.composition
                        (composition_type_id, upstream_process_id,
                         container_id, total_volume)
                     VALUES (%s, %s, %s, %s)
                     RETURNING composition_id"""
            TRN.add(sql, [ct_id, process.process_id, container.container_id,
                          volume])
            composition_id = TRN.execute_fetchlast()
        return composition_id

    def _get_composition_attr(self, attr):
        """Returns the value of the given composition attribute

        Parameters
        ----------
        attr : str
            The attribute to retrieve

        Returns
        -------
        Object
            The attribute
        """
        with sql_connection.TRN as TRN:
            sql = """SELECT {}
                     FROM qiita.composition
                        JOIN {} USING (composition_id)
                     WHERE {} = %s""".format(attr, self._table,
                                             self._id_column)
            TRN.add(sql, [self.id])
            return TRN.execute_fetchlast()

    @property
    def upstream_process(self):
        """The last process applied to the composition"""
        return process.Process.factory(
            self._get_composition_attr('upstream_process_id'))

    @property
    def container(self):
        """The container where the composition is stored"""
        return container_mod.Container.factory(
            self._get_composition_attr('container_id'))

    @property
    def total_volume(self):
        """The composition total volume"""
        return self._get_composition_attr('total_volume')

    @property
    def notes(self):
        """The composition notes"""
        return self._get_composition_attr('notes')

    @property
    def composition_id(self):
        return self._get_composition_attr('composition_id')


class ReagentComposition(Composition):
    """Reagent composition class

    Attributes
    ----------
    external_lot_id
    reagent_type

    See Also
    --------
    Composition
    """
    _table = 'qiita.reagent_composition'
    _id_column = 'reagent_composition_id'
    _composition_type = 'reagent'

    @staticmethod
    def list_reagents(reagent_type=None, term=None):
        """Generates a list of reagents

        Parameters
        ----------
        reagent_type: str, optional
            If provided, limit the plate list to the given type
        term: str, optional
            If provided, return only those reagents containing the given term

        Returns
        -------
        list of str
            The reagents external ids
        """
        with sql_connection.TRN as TRN:
            sql_where = ""
            sql_args = None
            if reagent_type and term:
                sql_where = ("WHERE description = %s AND "
                             "external_lot_id LIKE %s")
                sql_args = [reagent_type, '%{}%'.format(term)]
            elif reagent_type:
                sql_where = "WHERE description = %s"
                sql_args = [reagent_type]
            elif term:
                sql_where = "WHERE external_lot_id LIKE %s"
                sql_args = ['%{}%'.format(term)]

            sql = """SELECT external_lot_id
                     FROM qiita.reagent_composition
                        JOIN qiita.reagent_composition_type
                            USING (reagent_composition_type_id)
                     {}
                     ORDER BY external_lot_id""".format(sql_where)
            TRN.add(sql, sql_args)
            return TRN.execute_fetchflatten()

    @classmethod
    def from_external_id(cls, external_id):
        """Returns the ReagentComposition corresponding to the external id

        Parameters
        ----------
        external_id : str
            The external id of the reagent composition

        Returns
        -------
        ReagentComposition
            The reagent composition

        Raises
        ------
        LabmanUnknownIdError
            If no reagent composition exists with the given external id
        """
        with sql_connection.TRN as TRN:
            sql = """SELECT reagent_composition_id
                     FROM qiita.reagent_composition
                     WHERE external_lot_id = %s"""
            TRN.add(sql, [external_id])
            res = TRN.execute_fetchindex()
            if not res:
                raise exceptions_mod.LabmanUnknownIdError(
                    'ReagentComposition', external_id)
            return cls(res[0][0])

    @classmethod
    def create(cls, process, container, volume, reagent_type, external_lot_id):
        """Creates a new reagent composition

        Parameters
        ----------
        process : labman.db.process.Process
            The process that created the reagents
        container: labman.db.container.Container
            The container where the composition is stored
        volume: float
            The composition volume
        reagent_type: string
            The reagent type
        external_lot_id : str
            The external lot id

        Returns
        -------
        labman.db.composition.ReagentComposition
        """
        with sql_connection.TRN as TRN:
            # Add the row into the composition table
            composition_id = cls._common_creation_steps(
                process, container, volume)
            # Get the reagent composition type
            sql = """SELECT reagent_composition_type_id
                     FROM qiita.reagent_composition_type
                     WHERE description = %s"""
            TRN.add(sql, [reagent_type])
            rct_id = TRN.execute_fetchlast()

            # Add the row into the reagent composition table
            sql = """INSERT INTO qiita.reagent_composition
                        (composition_id, reagent_composition_type_id,
                         external_lot_id)
                     VALUES (%s, %s, %s)
                     RETURNING reagent_composition_id"""
            TRN.add(sql, [composition_id, rct_id, external_lot_id])
            rc_id = TRN.execute_fetchlast()
        return cls(rc_id)

    @property
    def external_lot_id(self):
        """The external lot id of the reagent"""
        return self._get_attr('external_lot_id')

    @property
    def reagent_type(self):
        """The reagent type"""
        with sql_connection.TRN as TRN:
            sql = """SELECT description
                     FROM qiita.reagent_composition_type
                        JOIN qiita.reagent_composition
                            USING (reagent_composition_type_id)
                     WHERE reagent_composition_id = %s"""
            TRN.add(sql, [self.id])
            return TRN.execute_fetchlast()


class PrimerComposition(Composition):
    """Primer composition class

    See Also
    --------
    Composition
    """
    _table = 'qiita.primer_composition'
    _id_column = 'primer_composition_id'
    _composition_type = 'primer'

    @property
    def primer_set_composition(self):
        """The primer set composition"""
        return PrimerSetComposition(
            self._get_attr('primer_set_composition_id'))


class PrimerSetComposition(Composition):
    """Primer set composition class

    See Also
    --------
    Composition
    """
    _table = 'qiita.primer_set_composition'
    _id_column = 'primer_set_composition_id'
    _composition_type = 'primer set'

    @property
    def barcode(self):
        """The barcode sequence"""
        return self._get_attr('barcode_seq')

    @property
    def external_id(self):
        """The external id"""
        return self._get_attr('external_id')


class SampleComposition(Composition):
    """Sample composition class

    Attributes
    ----------
    content_id
    content_type

    See Also
    --------
    Composition
    """
    _table = 'qiita.sample_composition'
    _id_column = 'sample_composition_id'
    _composition_type = 'sample'

    @staticmethod
    def get_control_samples(term=None):
        """Returns a list of control samples

        Parameters
        ----------
        term: str, optional
            If provided, return only those samples containing the given term

        Returns
        -------
        list of str
            The control samples
        """
        with sql_connection.TRN as TRN:
            sql_term = ""
            sql_args = None
            if term is not None:
                sql_term = "AND description LIKE %s"
                sql_args = ['%{}%'.format(term.lower())]
            sql = """SELECT description
                     FROM qiita.sample_composition_type
                     WHERE description != 'experimental sample'
                     {}
                     ORDER BY description""".format(sql_term)
            TRN.add(sql, sql_args)
            return TRN.execute_fetchflatten()

    @staticmethod
    def _get_sample_composition_type_id(compostion_type):
        """Returns the id of the sample composition type

        Returns
        -------
        int
            The id of the sample composition type
        """
        with sql_connection.TRN as TRN:
            sql = """SELECT sample_composition_type_id
                     FROM qiita.sample_composition_type
                     WHERE description = %s"""
            TRN.add(sql, [compostion_type])
            sct_id = TRN.execute_fetchlast()
        return sct_id

    @classmethod
    def create(cls, process, container, volume):
        """Creates a new blank sample composition

        Parameters
        ----------
        process: labman.db.process.Process
            The process creating the SampleComposition
        container: labman.db.container.Container
            The container where the sample composition is going to be held
        volume: float
            The initial sample composition volume

        Returns
        -------
        SampleComposition
            The newly created sample composition
        """
        with sql_connection.TRN as TRN:
            # Add the row into the composition table
            composition_id = cls._common_creation_steps(process, container,
                                                        volume)

            # Get the sample composition type id
            sct_id = cls._get_sample_composition_type_id('blank')

            # Add the row into the sample composition table
            sql = """INSERT INTO qiita.sample_composition
                        (composition_id, sample_composition_type_id)
                     VALUES (%s, %s)
                     RETURNING sample_composition_id"""
            TRN.add(sql, [composition_id, sct_id])
            sc_id = TRN.execute_fetchlast()
        return cls(sc_id)

    @property
    def sample_id(self):
        """The sample id"""
        return self._get_attr('sample_id')

    @property
    def sample_composition_type(self):
        """The content type"""
        with sql_connection.TRN as TRN:
            sql = """SELECT description
                     FROM qiita.sample_composition_type
                        JOIN qiita.sample_composition
                            USING (sample_composition_type_id)
                     WHERE sample_composition_id = %s"""
            TRN.add(sql, [self.id])
            return TRN.execute_fetchlast()

    @property
    def content(self):
        """The content of the sample composition"""
        sid = self.sample_id
        return sid if sid is not None else self.sample_composition_type

    def update(self, content):
        """Updates the contents of the sample composition

        Parameters
        ----------
        content: str
            The new contents of the SampleComposition
        """
        with sql_connection.TRN as TRN:
            # First check if the previous content matches the new one. If the
            # previous content is a experimental sample, then to be the same
            # content the sample_id mush match. If it is not an experimental
            # sample, then the sample composition type must match
            sc_type = self.sample_composition_type
            if not ((sc_type == 'experimental sample' and
                     self.sample_id == content) or (sc_type == 'content')):
                # The contents are different, we need to update
                # Identify if the content is a control or experimental sample
                sql = """SELECT sample_composition_type_id
                         FROM qiita.sample_composition_type
                         WHERE description = %s"""
                TRN.add(sql, [content])
                res = TRN.execute_fetchindex()
                if res:
                    # The content is a control
                    # res[0][0] -> Only 1 row and 1 column as result from the
                    # previous SQL query
                    sql_args = [res[0][0], None, self.id]
                else:
                    # The content is a sample
                    es_sci = self._get_sample_composition_type_id(
                        'experimental sample')
                    sql_args = [es_sci, content, self.id]

                sql = """UPDATE qiita.sample_composition
                         SET sample_composition_type_id = %s,
                             sample_id = %s
                         WHERE sample_composition_id = %s"""
                TRN.add(sql, sql_args)
                TRN.execute()


class GDNAComposition(Composition):
    """gDNA composition class

    Attributes
    ----------
    sample_composition

    See Also
    --------
    Composition
    """
    _table = 'qiita.gdna_composition'
    _id_column = 'gdna_composition_id'
    _composition_type = 'gDNA'

    @classmethod
    def create(cls, process, container, volume, sample_composition):
        """Creates a new gDNA composition

        Parameters
        ----------
        process: labman.db.process.Process
            The process creating the gDNA composition
        container: labman.db.container.Container
            The container with the composition
        volume: float
            The initial volume
        sample_composition: labman.db.composition.SampleComposition
            The origin sample composition the new gDNA composition has been
            derived from
        """
        with sql_connection.TRN as TRN:
            # Add the row into the composition table
            composition_id = cls._common_creation_steps(process, container,
                                                        volume)
            # Add the row into the gdna composition table
            sql = """INSERT INTO qiita.gdna_composition
                        (composition_id, sample_composition_id)
                     VALUES (%s, %s)
                     RETURNING gdna_composition_id"""
            TRN.add(sql, [composition_id, sample_composition.id])
            gdnac_id = TRN.execute_fetchlast()
        return cls(gdnac_id)

    @property
    def sample_composition(self):
        return SampleComposition(self._get_attr('sample_composition_id'))


class LibraryPrep16SComposition(Composition):
    """16S Library Preparation composition class

    Attributes
    ----------
    gdna_composition
    primer_composition

    See Also
    --------
    Composition
    """
    _table = 'qiita.library_prep_16s_composition'
    _id_column = 'library_prep_16s_composition_id'
    _composition_type = '16S library prep'

    @classmethod
    def create(cls, process, container, volume, gdna_composition,
               primer_composition):
        """Creates a new library prep 16S composition

        Parameters
        ----------
        process: labman.db.process.Process
            The process creating the composition
        container: labman.db.container.Container
            The container with the composition
        volume: float
            The initial volume
        gdna_composition: labman.db.composition.GDNAComposition
            The source gDNA composition
        primer_composition: labman.db.composition.PrimerComposition
            The source primer composition

        Returns
        -------
        labman.db.composition.LibraryPrep16SComposition
            The newly created composition
        """
        with sql_connection.TRN as TRN:
            # Add the row into the composition table
            composition_id = cls._common_creation_steps(process, container,
                                                        volume)
            # Add the row into the library prep 16S composition table
            sql = """INSERT INTO qiita.library_prep_16s_composition
                        (composition_id, gdna_composition_id,
                         primer_composition_id)
                     VALUES (%s, %s, %s)
                     RETURNING library_prep_16s_composition_id"""
            TRN.add(sql, [composition_id, gdna_composition.id,
                          primer_composition.id])
            lp16sc_id = TRN.execute_fetchlast()
        return cls(lp16sc_id)

    @property
    def gdna_composition(self):
        return GDNAComposition(self._get_attr('gdna_composition_id'))

    @property
    def primer_composition(self):
        return PrimerComposition(self._get_attr('primer_composition_id'))


class NormalizedGDNAComposition(Composition):
    """Normalized gDNA composition class

    Attributes
    ----------
    gdna_composition

    See Also
    --------
    Composition
    """
    _table = 'qiita.normalized_gdna_composition'
    _id_column = 'normalized_gdna_composition_id'
    _composition_type = 'normalized gDNA'

    @classmethod
    def create(cls, process, container, volume, gdna_composition, dna_vol,
               water_vol):
        """Creates a new normalized gDNA composition

        Parameters
        ----------
        process: labman.db.process.Process
            The process creating the composition
        container: labman.db.container.Container
            The container with the composition
        volume: float
            The initial volume
        gdna_composition: labman.db.composition.GDNAComposition
            The source gDNA composition
        dna_vol: float
            The amount of DNA used
        water_vol: float
            The amount of water used

        Returns
        -------
        labman.db.composition.NormalizedGDNAComposition
            The newly created composition
        """
        with sql_connection.TRN as TRN:
            # Add the row into the composition table
            composition_id = cls._common_creation_steps(
                process, container, volume)
            # Add the row into the normalized gdna composition table
            sql = """INSERT INTO qiita.normalized_gdna_composition
                        (composition_id, gdna_composition_id, dna_volume,
                         water_volume)
                     VALUES (%s, %s, %s, %s)
                     RETURNING normalized_gdna_composition_id"""
            TRN.add(sql, [composition_id, gdna_composition.id,
                          dna_vol, water_vol])
            ngdnac_id = TRN.execute_fetchlast()
        return cls(ngdnac_id)

    @property
    def gdna_composition(self):
        return GDNAComposition(self._get_attr('gdna_composition_id'))

    @property
    def dna_volume(self):
        return self._get_attr('dna_volume')

    @property
    def water_volume(self):
        return self._get_attr('water_volume')


class LibraryPrepShotgunComposition(Composition):
    """Shotgun Library Preparation composition class

    Attributes
    ----------
    normalized_gdna_composition
    i5_composition
    i7_composition

    See Also
    --------
    Composition
    """
    _table = 'qiita.library_prep_shotgun_composition'
    _id_column = 'library_prep_shotgun_composition_id'
    _composition_type = 'shotgun library prep'

    @classmethod
    def create(cls, process, container, volume, norm_gdna_composition,
               i5_composition, i7_composition):
        """Creates a new library prep shotgun composition

        Parameters
        ----------
        process: labman.db.process.Process
            The process creating the composition
        container: labman.db.container.Container
            The container with the composition
        volume: float
            The initial volume
        norm_gdna_composition: labman.db.composition.NormalizedGDNAComposition
            The source normalized gDNA composition
        i5_composition: labman.db.composition.PrimerComposition
            The i5 composition
        i7_composition: labman.db.composition.PrimerComposition
            The i5 composition

        Returns
        -------
        labman.db.composition.LibraryPrepShotgunComposition
            The newly created composition
        """
        with sql_connection.TRN as TRN:
            # Add the row into the composition table
            composition_id = cls._common_creation_steps(process, container,
                                                        volume)
            # Add the row into the library prep shotgun composition table
            sql = """INSERT INTO qiita.library_prep_shotgun_composition
                        (composition_id, normalized_gdna_composition_id,
                         i5_primer_composition_id, i7_primer_composition_id)
                     VALUES (%s, %s, %s, %s)
                     RETURNING library_prep_shotgun_composition_id"""
            TRN.add(sql, [composition_id, norm_gdna_composition.id,
                          i5_composition.id, i7_composition.id])
            lpsc_id = TRN.execute_fetchlast()
        return cls(lpsc_id)

    @property
    def normalized_gdna_composition(self):
        return NormalizedGDNAComposition(
            self._get_attr('normalized_gdna_composition_id'))

    @property
    def i5_composition(self):
        return PrimerComposition(self._get_attr('i5_primer_composition_id'))

    @property
    def i7_composition(self):
        return PrimerComposition(self._get_attr('i7_primer_composition_id'))


class PoolComposition(Composition):
    """Pool composition class

    Attributes
    ----------
    components

    See Also
    --------
    Composition
    """
    _table = 'qiita.pool_composition'
    _id_column = 'pool_composition_id'
    _composition_type = 'pool'

    @staticmethod
    def list_pools():
        """Generates a list of pools with some information about them

        Returns
        -------
        list of dicts
            The list of pool information with the structure:
            [{'pool_id': int, 'external_id': string}]
        """
        with sql_connection.TRN as TRN:
            sql = """SELECT pool_composition_id, external_id
                     FROM qiita.pool_composition
                        JOIN qiita.composition USING (composition_id)
                        JOIN qiita.tube USING (container_id)
                     ORDER BY pool_composition_id"""
            TRN.add(sql)
            return [dict(r) for r in TRN.execute_fetchindex()]

    @classmethod
    def create(cls, process, container, volume):
        """Creates a new pool composition

        Parameters
        ----------
        process: labman.db.process.Process
            The process creating the composition
        container: labman.db.container.Container
            The container with the composition
        volume: float
            The initial volume

        Returns
        -------
        labman.db.composition.PoolComposition
            The newly created composition
        """
        with sql_connection.TRN as TRN:
            # Add the row into the composition table
            composition_id = cls._common_creation_steps(process, container,
                                                        volume)
            # Add the row into the pool composition table
            sql = """INSERT INTO qiita.pool_composition (composition_id)
                     VALUES (%s)
                     RETURNING pool_composition_id"""
            TRN.add(sql, [composition_id])
            pc_id = TRN.execute_fetchlast()
        return cls(pc_id)

    @property
    def components(self):
        with sql_connection.TRN as TRN:
            sql = """SELECT input_composition_id, input_volume as volume,
                            percentage_of_output as percentage
                     FROM qiita.pool_composition_components
                     WHERE output_pool_composition_id = %s"""
            TRN.add(sql, [self.id])
            result = []
            for res in TRN.execute_fetchindex():
                result.append(
                    {'composition': Composition.factory(
                        res['input_composition_id']),
                     'input_volume': res['volume'],
                     'percentage_of_output': res['percentage']})
        return result


class PrimerSet(base.LabmanObject):
    """Primer set class

    Attributes
    ----------
    external_id
    target_name
    notes
    """
    _table = 'qiita.primer_set'
    _id_column = 'primer_set_id'

    @property
    def external_id(self):
        return self._get_attr('external_id')

    @property
    def target_name(self):
        return self._get_attr('target_name')

    @property
    def notes(self):
        return self._get_attr('notes')


class ShotgunPrimerSet(base.LabmanObject):
    """Shotgun primer set class

    Attributes
    ----------
    external_id
    current_combo_index

    Methods
    -------
    get_next_combos
    """
    _table = 'qiita.shotgun_primer_set'
    _id_column = 'shotgun_primer_set_id'

    @property
    def external_id(self):
        return self._get_attr('external_id')

    @property
    def current_combo_index(self):
        return self._get_attr('current_combo_index')

    def get_next_combos(self, n):
        """Get the next n i5-i7 primer combo to use

        Parameters
        ----------
        n: int
            The number of combos to return

        Returns
        -------
        list of (PrimerSetComposition, PrimerSetComposition)

        Raises
        ------
        ValueError
            If n is not between 1 and the total number of combos available
            for the primer set (both ends included)
        """
        with sql_connection.TRN as TRN:
            # Check that we can fullfill the number of combos requested
            sql = """SELECT COUNT(1)
                     FROM qiita.shotgun_combo_primer_set
                     WHERE shotgun_primer_set_id = %s"""
            TRN.add(sql, [self.id])
            total_combos = TRN.execute_fetchlast()

            if not (1 <= n <= total_combos):
                raise ValueError(
                    'Cannot retrieve %s combos for primer set "%s". Please '
                    'provide a number between 1 and %s'
                    % (n, self.external_id, total_combos))

            # Retrieve the number of combos that we need
            # We are not going to execute more than 2 iterations of the loop
            # below. A loop is required to cover the case in which we need
            # to start the combo list fromm the top. The if statement above
            # ensures that we are not going to reach the end of the list twice
            # and hence only execute, at most, 2 iterations of the for loop
            result = []
            while n > 0:
                idx = self.current_combo_index
                # Retrieve the combos
                sql = """SELECT i5_primer_set_composition_id,
                                i7_primer_set_composition_id
                         FROM qiita.shotgun_combo_primer_set
                         WHERE shotgun_primer_set_id = %s
                         ORDER BY shotgun_primer_set_id
                         OFFSET %s LIMIT %s"""
                TRN.add(sql, [self.id, idx, n])
                records = TRN.execute_fetchindex()

                # Add the objects to the result list
                result.extend([
                    (PrimerSetComposition(r[0]), PrimerSetComposition(r[1]))
                    for r in records])

                # Compute the new index and update the database
                new_idx = (idx + len(records)) % total_combos
                sql = """UPDATE qiita.shotgun_primer_set
                         SET current_combo_index = %s
                         WHERE shotgun_primer_set_id = %s"""
                TRN.add(sql, [new_idx, self.id])

                # Update n (loop invariant)
                n = n - len(records)

        return result
