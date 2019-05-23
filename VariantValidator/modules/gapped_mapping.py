import copy
import re

import hgvs.exceptions

from . import vvFunctions as fn
from . import vvHGVS
from .vvLogging import logger


class GapMapper(object):

    def __init__(self, variant, validator):
        """
        Sets initial values
        :param variant: variant.Variant()
        :param validator: Validator()
        """
        self.variant = variant
        self.validator = validator

        self.gapped_transcripts = ''
        self.auto_info = ''
        self.orientation = None
        self.hgvs_genomic_possibilities = []
        self.disparity_deletion_in = []

        self.hgvs_genomic_5pr = None
        self.tx_hgvs_not_delins = None

    def gapped_g_to_c(self, rel_var):
        """
        Gap aware projection from g. to c.
        """

        # Set variables for problem specific warnings
        gapped_alignment_warning = ''
        corrective_action_taken = ''
        self.gapped_transcripts = ''
        self.auto_info = ''
        self.disparity_deletion_in = []

        # Create a pseudo VCF so that normalization can be applied and a delins can be generated
        hgvs_genomic_variant = self.variant.hgvs_genomic
        # Reverse normalize hgvs_genomic_variant: NOTE will replace ref
        reverse_normalized_hgvs_genomic = self.variant.reverse_normalizer.normalize(hgvs_genomic_variant)
        self.hgvs_genomic_5pr = copy.deepcopy(reverse_normalized_hgvs_genomic)

        # VCF
        vcf_dict = vvHGVS.hgvs2vcf(reverse_normalized_hgvs_genomic, self.variant.primary_assembly,
                                   self.variant.reverse_normalizer, self.validator.sf)
        pos = vcf_dict['pos']
        ref = vcf_dict['ref']
        alt = vcf_dict['alt']

        # Generate an end position
        end = str(int(pos) + len(ref) - 1)
        pos = str(pos)

        # take a look at the input genomic variant for potential base salvage
        stash_ac = vcf_dict['chr']
        stash_pos = int(vcf_dict['pos'])
        stash_ref = vcf_dict['ref']
        stash_alt = vcf_dict['alt']
        stash_end = end
        stash_input = str(self.variant.post_format_conversion)
        # Re-Analyse genomic positions
        if 'NG_' in str(self.variant.hgvs_formatted):
            c = self.validator.hp.parse_hgvs_variant(rel_var[0])
            if hasattr(c.posedit.edit, 'ref') and c.posedit.edit.ref is not None:
                c.posedit.edit.ref = c.posedit.edit.ref.upper()
            if hasattr(c.posedit.edit, 'alt') and c.posedit.edit.alt is not None:
                c.posedit.edit.alt = c.posedit.edit.alt.upper()
            stash_input = self.validator.myevm_t_to_g(c, self.variant.no_norm_evm,
                                                      self.variant.primary_assembly, self.variant.hn)
        if 'NC_' in str(stash_input) or 'NT_' in str(stash_input) or 'NW_' in str(stash_input):
            try:
                hgvs_stash = self.validator.hp.parse_hgvs_variant(stash_input)
            except:
                hgvs_stash = stash_input
            if hasattr(hgvs_stash.posedit.edit, 'ref') and hgvs_stash.posedit.edit.ref is not None:
                hgvs_stash.posedit.edit.ref = hgvs_stash.posedit.edit.ref.upper()
            if hasattr(hgvs_stash.posedit.edit, 'alt') and hgvs_stash.posedit.edit.alt is not None:
                hgvs_stash.posedit.edit.alt = hgvs_stash.posedit.edit.alt.upper()

            # MAKE A NO NORM HGVS2VCF
            stash_dict = vvHGVS.pos_lock_hgvs2vcf(hgvs_stash, self.variant.primary_assembly,
                                                  self.variant.reverse_normalizer, self.validator.sf)
            stash_ac = hgvs_stash.ac
            stash_pos = int(stash_dict['pos'])
            stash_ref = stash_dict['ref']
            stash_alt = stash_dict['alt']
            # Generate an end position
            stash_end = str(stash_pos + len(stash_ref) - 1)

        # Store a not real deletion insertion
        stored_hgvs_not_delins = self.validator.hp.parse_hgvs_variant(self.hgvs_genomic_5pr.ac + ':' +
            self.hgvs_genomic_5pr.type + '.' + pos + '_' + end + 'del' + ref + 'ins' + alt)
        assert stored_hgvs_not_delins != ''
        stash_hgvs_not_delins = self.validator.hp.parse_hgvs_variant(stash_ac + ':' +
            self.hgvs_genomic_5pr.type + '.' + str(stash_pos) + '_' + stash_end + 'del' + stash_ref + 'ins' + stash_alt)

        # make an empty rel_var
        nw_rel_var = []

        # loop through rel_var and amend where required
        for var in rel_var:
            # Store the current hgvs:c. description
            saved_hgvs_coding = self.validator.hp.parse_hgvs_variant(var)

            # Remove un-selected transcripts
            if self.validator.select_transcripts != 'all':
                tx_ac = saved_hgvs_coding.ac
                # If it's in the selected tx dict, keep it
                if tx_ac.split('.')[0] in list(self.validator.select_transcripts_dict.keys()):
                    pass
                # If not get rid of it!
                else:
                    continue

            # Get orientation of the gene wrt genome and a list of exons mapped to the genome
            ori = self.validator.tx_exons(tx_ac=saved_hgvs_coding.ac, alt_ac=self.hgvs_genomic_5pr.ac,
                                          alt_aln_method=self.validator.alt_aln_method)
            self.orientation = int(ori[0]['alt_strand'])
            intronic_variant = 'false'

            hgvs_seek_var = self.get_hgvs_seek_var(self.variant.hgvs_genomic, saved_hgvs_coding)

            if (hgvs_seek_var.posedit.pos.start.base + hgvs_seek_var.posedit.pos.start.offset) > (
                    saved_hgvs_coding.posedit.pos.start.base + saved_hgvs_coding.posedit.pos.start.offset) and (
                    hgvs_seek_var.posedit.pos.end.base + hgvs_seek_var.posedit.pos.end.offset) > (
                    saved_hgvs_coding.posedit.pos.end.base + saved_hgvs_coding.posedit.pos.end.offset):
                pass
            else:
                hgvs_seek_var = saved_hgvs_coding

            try:
                self.variant.hn.normalize(hgvs_seek_var)
            except hgvs.exceptions.HGVSUnsupportedOperationError as e:
                error = str(e)
                if 'Normalization of intronic variants is not supported' in error or \
                        'Unsupported normalization of variants spanning the exon-intron boundary' in error:
                    if 'Unsupported normalization of variants spanning the exon-intron boundary' in error:
                        intronic_variant = 'hard_fail'
                    else:
                        # Double check to see whether the variant is actually intronic?
                        for exon in ori:
                            genomic_start = int(exon['alt_start_i'])
                            genomic_end = int(exon['alt_end_i'])
                            if genomic_start < self.hgvs_genomic_5pr.posedit.pos.start.base <= genomic_end and \
                                    genomic_start < self.hgvs_genomic_5pr.posedit.pos.end.base <= genomic_end:
                                intronic_variant = 'false'
                                break
                            else:
                                intronic_variant = 'true'

            # if intronic_variant != 'hard_fail':
            #     if re.search(r'\d+\+', str(hgvs_seek_var.posedit.pos)) or re.search(r'\d+\-', str(
            #             hgvs_seek_var.posedit.pos)) or re.search(r'\*\d+\+', str(
            #             hgvs_seek_var.posedit.pos)) or re.search(r'\*\d+\-', str(hgvs_seek_var.posedit.pos)):
            #         # Double check to see whether the variant is actually intronic?
            #         for exon in ori:
            #             genomic_start = int(exon['alt_start_i'])
            #             genomic_end = int(exon['alt_end_i'])
            #             if (genomic_start < self.hgvs_genomic_5pr.posedit.pos.start.base <= genomic_end) and (
            #                     genomic_start < self.hgvs_genomic_5pr.posedit.pos.end.base <= genomic_end):
            #                 intronic_variant = 'false'
            #                 break
            #             else:
            #                 intronic_variant = 'true'

            if re.search(r'\d+\+', str(hgvs_seek_var.posedit.pos)) or re.search(r'\d+-', str(
                    hgvs_seek_var.posedit.pos)) or re.search(r'\*\d+\+', str(
                    hgvs_seek_var.posedit.pos)) or re.search(r'\*\d+-', str(hgvs_seek_var.posedit.pos)):
                # Double check to see whether the variant is actually intronic?
                for exon in ori:
                    genomic_start = int(exon['alt_start_i'])
                    genomic_end = int(exon['alt_end_i'])
                    if (genomic_start < self.hgvs_genomic_5pr.posedit.pos.start.base <= genomic_end) and (
                            genomic_start < self.hgvs_genomic_5pr.posedit.pos.end.base <= genomic_end):
                        intronic_variant = 'false'
                        break
                    else:
                        intronic_variant = 'true'

            # If exonic, process
            if intronic_variant != 'true':

                # Attempt to find gaps in reference sequence by catching disparity in genome length and
                # overlapping transcript lengths
                self.disparity_deletion_in = ['false', 'false']
                hgvs_not_delins = ''
                if stored_hgvs_not_delins != '':
                    # Refresh hgvs_not_delins from stored_hgvs_not_delins
                    hgvs_not_delins = self.dup_ins_5prime_shift(stored_hgvs_not_delins, saved_hgvs_coding)

                    try:
                        self.tx_hgvs_not_delins = self.variant.no_norm_evm.g_to_n(hgvs_not_delins, saved_hgvs_coding.ac)
                    except hgvs.exceptions.HGVSInvalidIntervalError:
                        self.tx_hgvs_not_delins = self.variant.no_norm_evm.g_to_n(self.hgvs_genomic_5pr, saved_hgvs_coding.ac)
                    except hgvs.exceptions.HGVSError as e:
                        if str(e) == 'start or end or both are beyond the bounds of transcript record':
                            self.tx_hgvs_not_delins = saved_hgvs_coding

                    # Create normalized version of tx_hgvs_not_delins
                    rn_tx_hgvs_not_delins = copy.deepcopy(self.tx_hgvs_not_delins)
                    # Check for +ve base and adjust
                    if ('+' in str(rn_tx_hgvs_not_delins.posedit.pos.start) or '-' in str(rn_tx_hgvs_not_delins.posedit.pos.start)) and (
                            '+' in str(rn_tx_hgvs_not_delins.posedit.pos.end) or '-' in str(rn_tx_hgvs_not_delins.posedit.pos.end)):
                        rn_tx_hgvs_not_delins = self.remove_offsetting_to_span_gap(rn_tx_hgvs_not_delins)

                    elif '+' in str(rn_tx_hgvs_not_delins.posedit.pos.end):
                        rn_tx_hgvs_not_delins, hgvs_not_delins = self.move_tx_end_base_to_next_nonoffset(
                            rn_tx_hgvs_not_delins, saved_hgvs_coding, back=False)

                    elif '+' in str(rn_tx_hgvs_not_delins.posedit.pos.start):
                        rn_tx_hgvs_not_delins, hgvs_not_delins = self.move_tx_start_base_to_previous_nonoffset(
                            rn_tx_hgvs_not_delins, saved_hgvs_coding)

                    # Check for -ve base and adjust
                    elif '-' in str(rn_tx_hgvs_not_delins.posedit.pos.end) and '-' in str(rn_tx_hgvs_not_delins.posedit.pos.start):
                        rn_tx_hgvs_not_delins = self.remove_offsetting_to_span_gap(rn_tx_hgvs_not_delins)

                    elif '-' in str(rn_tx_hgvs_not_delins.posedit.pos.end):
                        rn_tx_hgvs_not_delins, hgvs_not_delins = self.move_tx_end_base_to_next_nonoffset(
                            rn_tx_hgvs_not_delins, saved_hgvs_coding)

                    elif '-' in str(rn_tx_hgvs_not_delins.posedit.pos.start):
                        rn_tx_hgvs_not_delins, hgvs_not_delins = self.move_tx_start_base_to_previous_nonoffset(
                            rn_tx_hgvs_not_delins, saved_hgvs_coding, with_base_subtract=True)

                    # Logic
                    if len(hgvs_not_delins.posedit.edit.ref) < len(rn_tx_hgvs_not_delins.posedit.edit.ref):
                        gap_length = len(rn_tx_hgvs_not_delins.posedit.edit.ref) - len(
                            hgvs_not_delins.posedit.edit.ref)
                        self.disparity_deletion_in = ['chromosome', gap_length]
                    elif len(hgvs_not_delins.posedit.edit.ref) > len(rn_tx_hgvs_not_delins.posedit.edit.ref):
                        gap_length = len(hgvs_not_delins.posedit.edit.ref) - len(
                            rn_tx_hgvs_not_delins.posedit.edit.ref)
                        self.disparity_deletion_in = ['transcript', gap_length]
                    else:
                        hgvs_stash_t = self.validator.vm.g_to_t(stash_hgvs_not_delins, saved_hgvs_coding.ac)
                        if len(stash_hgvs_not_delins.posedit.edit.ref) > len(hgvs_stash_t.posedit.edit.ref):
                            try:
                                self.variant.hn.normalize(hgvs_stash_t)
                            except:
                                fn.exceptPass()
                            else:
                                gap_length = len(stash_hgvs_not_delins.posedit.edit.ref) - len(
                                    hgvs_stash_t.posedit.edit.ref)
                                self.disparity_deletion_in = ['transcript', gap_length]
                                try:
                                    self.tx_hgvs_not_delins = self.validator.vm.c_to_n(hgvs_stash_t)
                                except:
                                    self.tx_hgvs_not_delins = hgvs_stash_t
                                hgvs_not_delins = stash_hgvs_not_delins
                        elif hgvs_stash_t.posedit.pos.start.offset != 0 or hgvs_stash_t.posedit.pos.end.offset != 0:
                            self.disparity_deletion_in = ['transcript', 'Requires Analysis']
                            try:
                                self.tx_hgvs_not_delins = self.validator.vm.c_to_n(hgvs_stash_t)
                            except:
                                self.tx_hgvs_not_delins = hgvs_stash_t
                            hgvs_not_delins = stash_hgvs_not_delins
                            self.hgvs_genomic_5pr = stash_hgvs_not_delins

                # Final sanity checks
                try:
                    self.validator.vm.g_to_t(hgvs_not_delins, self.tx_hgvs_not_delins.ac)
                except Exception as e:
                    if str(e) == 'start or end or both are beyond the bounds of transcript record':
                        hgvs_not_delins = saved_hgvs_coding
                        self.disparity_deletion_in = ['false', 'false']
                    logger.warning(str(e))
                try:
                    self.variant.hn.normalize(self.tx_hgvs_not_delins)
                except hgvs.exceptions.HGVSUnsupportedOperationError as e:
                    error = str(e)
                    if 'Normalization of intronic variants is not supported' in error or \
                            'Unsupported normalization of variants spanning the exon-intron boundary' in error:
                        if 'Unsupported normalization of variants spanning the exon-intron boundary' in error:
                            hgvs_not_delins = saved_hgvs_coding
                            self.disparity_deletion_in = ['false', 'false']
                        elif 'Normalization of intronic variants is not supported' in error:
                            # We know that this cannot be because of an intronic variant, so must be aligned to tx gap
                            self.disparity_deletion_in = ['transcript', 'Requires Analysis']
                    logger.warning(error)
                # Pre-processing of self.tx_hgvs_not_delins
                try:
                    if self.tx_hgvs_not_delins.posedit.edit.alt is None:
                        self.tx_hgvs_not_delins.posedit.edit.alt = ''
                except Exception as e:
                    if str(e) == "'Dup' object has no attribute 'alt'":
                        tx_hgvs_not_delins_delins_from_dup = fn.hgvs_dup2indel(self.tx_hgvs_not_delins)
                        self.tx_hgvs_not_delins = self.validator.hp.parse_hgvs_variant(tx_hgvs_not_delins_delins_from_dup)

                # GAP IN THE TRANSCRIPT DISPARITY DETECTED
                if self.disparity_deletion_in[0] == 'transcript':

                    gapped_alignment_warning = str(self.hgvs_genomic_5pr) + ' does not represent a true variant ' \
                        'because it is an artefact of aligning the transcripts listed below with genome build ' + \
                        self.variant.primary_assembly

                    # ANY VARIANT WHOLLY WITHIN THE GAP
                    hgvs_refreshed_variant = self.transcript_disparity(reverse_normalized_hgvs_genomic,
                                                                       stored_hgvs_not_delins, self.variant.hgvs_genomic, 1)

                # GAP IN THE CHROMOSOME
                elif self.disparity_deletion_in[0] == 'chromosome':
                    # Set warning variables
                    gapped_alignment_warning = str(self.hgvs_genomic_5pr) + ' does not represent a true variant ' \
                        'because it is an artefact of aligning the transcripts listed below with genome build ' + \
                        self.variant.primary_assembly
                    hgvs_refreshed_variant = self.tx_hgvs_not_delins
                    # Warn
                    self.auto_info += str(hgvs_refreshed_variant.ac) + ':c.' + str(hgvs_refreshed_variant.posedit.pos)+\
                        ' contains ' + str(self.disparity_deletion_in[1]) + ' transcript base(s) that fail to align ' \
                        'to chromosome ' + str(self.variant.hgvs_genomic.ac) + '\n'
                    self.gapped_transcripts = self.gapped_transcripts + str(hgvs_refreshed_variant.ac) + ' '
                else:
                    # Try the push
                    hgvs_stash = copy.deepcopy(stash_hgvs_not_delins)
                    stash_ac = hgvs_stash.ac
                    # Make a hard left and hard right not delins g.
                    stash_dict_right = vvHGVS.hard_right_hgvs2vcf(hgvs_stash, self.variant.primary_assembly,
                                                                  self.variant.hn, self.validator.sf)
                    stash_pos_right = int(stash_dict_right['pos'])
                    stash_ref_right = stash_dict_right['ref']
                    stash_alt_right = stash_dict_right['alt']
                    stash_end_right = str(stash_pos_right + len(stash_ref_right) - 1)
                    stash_hgvs_not_delins_right = self.validator.hp.parse_hgvs_variant(stash_ac + ':' +
                        hgvs_stash.type + '.' + str(stash_pos_right) + '_' + stash_end_right + 'del' +
                        stash_ref_right + 'ins' + stash_alt_right)
                    stash_dict_left = vvHGVS.hard_left_hgvs2vcf(hgvs_stash, self.variant.primary_assembly,
                                                                self.variant.reverse_normalizer, self.validator.sf)
                    stash_pos_left = int(stash_dict_left['pos'])
                    stash_ref_left = stash_dict_left['ref']
                    stash_alt_left = stash_dict_left['alt']
                    stash_end_left = str(stash_pos_left + len(stash_ref_left) - 1)
                    stash_hgvs_not_delins_left = self.validator.hp.parse_hgvs_variant(
                        stash_ac + ':' + hgvs_stash.type + '.' + str(
                            stash_pos_left) + '_' + stash_end_left + 'del' + stash_ref_left + 'ins' + stash_alt_left)
                    # Map in-situ to the transcript left and right
                    try:
                        tx_hard_right = self.validator.vm.g_to_t(stash_hgvs_not_delins_right, saved_hgvs_coding.ac)
                    except Exception:
                        tx_hard_right = saved_hgvs_coding
                    else:
                        normalize_stash_right = self.variant.hn.normalize(stash_hgvs_not_delins_right)
                        if str(normalize_stash_right.posedit) == str(stash_hgvs_not_delins.posedit):
                            tx_hard_right = saved_hgvs_coding
                    try:
                        tx_hard_left = self.validator.vm.g_to_t(stash_hgvs_not_delins_left, saved_hgvs_coding.ac)
                    except Exception:
                        tx_hard_left = saved_hgvs_coding
                    else:
                        normalize_stash_left = self.variant.hn.normalize(stash_hgvs_not_delins_left)
                        if str(normalize_stash_left.posedit) == str(stash_hgvs_not_delins.posedit):
                            tx_hard_left = saved_hgvs_coding
                    # The Logic - Currently limited to genome gaps
                    if len(stash_hgvs_not_delins_right.posedit.edit.ref) < len(tx_hard_right.posedit.edit.ref):
                        tx_hard_right = self.variant.hn.normalize(tx_hard_right)
                        gapped_alignment_warning = str(self.hgvs_genomic_5pr) + ' may be an artefact of aligning the ' \
                            'transcripts listed below with genome build ' + self.variant.primary_assembly
                        hgvs_refreshed_variant = tx_hard_right
                        self.gapped_transcripts = self.gapped_transcripts + str(tx_hard_right.ac) + ' '
                    elif len(stash_hgvs_not_delins_left.posedit.edit.ref) < len(tx_hard_left.posedit.edit.ref):
                        tx_hard_left = self.variant.hn.normalize(tx_hard_left)
                        gapped_alignment_warning = str(self.hgvs_genomic_5pr) + ' may be an artefact of aligning the ' \
                            'transcripts listed below with genome build ' + self.variant.primary_assembly
                        hgvs_refreshed_variant = tx_hard_left
                        self.gapped_transcripts = self.gapped_transcripts + str(tx_hard_left.ac) + ' '
                    else:
                        # Keep the same by re-setting rel_var
                        hgvs_refreshed_variant = saved_hgvs_coding

                # Edit the output
                hgvs_refreshed_variant = self.edit_output(hgvs_refreshed_variant, saved_hgvs_coding)

                # Send to empty nw_rel_var
                nw_rel_var.append(hgvs_refreshed_variant)

            # Otherwise these variants need to be set
            else:
                corrective_action_taken = ''
                gapped_alignment_warning = ''
                # Send to empty nw_rel_var
                nw_rel_var.append(saved_hgvs_coding)

        data = {
            'gapped_alignment_warning': gapped_alignment_warning,
            'corrective_action_taken': corrective_action_taken,
            'auto_info': self.auto_info,
            'disparity_deletion_in': self.disparity_deletion_in,
            'gapped_transcripts': self.gapped_transcripts
        }
        return data, nw_rel_var

    def g_to_t_compensation(self, ori, hgvs_coding, rec_var):
        self.orientation = int(ori[0]['alt_strand'])
        self.hgvs_genomic_possibilities = []
        hgvs_genomic = self.validator.myevm_t_to_g(hgvs_coding, self.variant.no_norm_evm, self.variant.primary_assembly,
                                                   self.variant.hn)

        logger.warning('g_to_t gap code 1 active')
        rn_hgvs_genomic = self.variant.reverse_normalizer.normalize(hgvs_genomic)
        self.hgvs_genomic_possibilities.append(rn_hgvs_genomic)

        try:
            if self.orientation != -1:
                chromosome_normalized_hgvs_coding = self.variant.reverse_normalizer.normalize(hgvs_coding)
            else:
                chromosome_normalized_hgvs_coding = self.variant.hn.normalize(hgvs_coding)
        except hgvs.exceptions.HGVSUnsupportedOperationError:
            chromosome_normalized_hgvs_coding = hgvs_coding

        most_3pr_hgvs_genomic = self.validator.myvm_t_to_g(chromosome_normalized_hgvs_coding, hgvs_genomic.ac,
                                                      self.variant.no_norm_evm, self.variant.hn)
        self.hgvs_genomic_possibilities.append(most_3pr_hgvs_genomic)

        # Push from side to side to try pick up odd placements
        # MAKE A NO NORM HGVS2VCF
        # First to the right
        hgvs_stash = copy.deepcopy(hgvs_coding)
        stash_tx_right = ''
        stash_tx_left = ''
        try:
            hgvs_stash = self.variant.no_norm_evm.c_to_n(hgvs_stash)
        except:
            fn.exceptPass()
        try:
            stash_ac = hgvs_stash.ac
            stash_dict = vvHGVS.hard_right_hgvs2vcf(hgvs_stash, self.variant.primary_assembly, self.variant.hn, self.validator.sf)
            stash_pos = int(stash_dict['pos'])
            stash_ref = stash_dict['ref']
            stash_alt = stash_dict['alt']
            # Generate an end position
            stash_end = str(stash_pos + len(stash_ref) - 1)
            # make a not real deletion insertion
            stash_hgvs_not_delins = self.validator.hp.parse_hgvs_variant(
                stash_ac + ':' + hgvs_stash.type + '.' + str(
                    stash_pos) + '_' + stash_end + 'del' + stash_ref + 'ins' + stash_alt)
            try:
                stash_hgvs_not_delins = self.variant.no_norm_evm.n_to_c(stash_hgvs_not_delins)
            except:
                fn.exceptPass()

            test_stash_tx_right = copy.deepcopy(stash_hgvs_not_delins)
            # stash_genomic = vm.t_to_g(test_stash_tx_right, hgvs_genomic.ac)
            stash_genomic = self.validator.myvm_t_to_g(test_stash_tx_right, hgvs_genomic.ac, self.variant.no_norm_evm,
                                                       self.variant.hn)
            # Stash the outputs if required
            # test variants = NC_000006.11:g.90403795G= (causes double identity)
            #                 NC_000002.11:g.73675227_73675228insCTC (? incorrect assumed insertion position)
            #                 NC_000003.11:g.14561629_14561630GC= NC_000003.11:g.14561629_14561630insG (Odd gap position)
            # if test_stash_tx_right.posedit.edit.type == 'identity' and stash_genomic.posedit.edit.type == 'identity':
            # pass
            if len(test_stash_tx_right.posedit.edit.ref) == (
                    (stash_genomic.posedit.pos.end.base - stash_genomic.posedit.pos.start.base) + 1):
                stash_tx_right = test_stash_tx_right
                if hasattr(test_stash_tx_right.posedit.edit,
                           'alt') and test_stash_tx_right.posedit.edit.alt is not None:
                    alt = test_stash_tx_right.posedit.edit.alt
                else:
                    alt = ''
                if hasattr(stash_genomic.posedit.edit,
                           'alt') and stash_genomic.posedit.edit.alt is not None:
                    g_alt = stash_genomic.posedit.edit.alt
                else:
                    g_alt = ''
                if (len(alt) - (
                        test_stash_tx_right.posedit.pos.end.base - test_stash_tx_right.posedit.pos.start.base) + 1) != (
                        len(g_alt) - (
                        stash_genomic.posedit.pos.end.base - stash_genomic.posedit.pos.start.base) + 1):
                    self.hgvs_genomic_possibilities.append(stash_genomic)
                else:
                    self.hgvs_genomic_possibilities.append('')
            elif test_stash_tx_right.posedit.edit.type == 'identity':
                reform_ident = str(test_stash_tx_right).split(':')[0]
                reform_ident = reform_ident + ':c.' + str(test_stash_tx_right.posedit.pos) + 'del' + str(
                    test_stash_tx_right.posedit.edit.ref)  # + 'ins' + str(test_stash_tx_right.posedit.edit.alt)
                hgvs_reform_ident = self.validator.hp.parse_hgvs_variant(reform_ident)
                try:
                    self.variant.hn.normalize(hgvs_reform_ident)
                except hgvs.exceptions.HGVSError as e:
                    error = str(e)
                    if re.search('spanning the exon-intron boundary', error):
                        stash_tx_right = test_stash_tx_right
                        self.hgvs_genomic_possibilities.append('')
                else:
                    stash_tx_right = test_stash_tx_right
                    self.hgvs_genomic_possibilities.append(stash_genomic)
            else:
                try:
                    self.variant.hn.normalize(test_stash_tx_right)
                except hgvs.exceptions.HGVSUnsupportedOperationError:
                    self.hgvs_genomic_possibilities.append('')
                else:
                    stash_tx_right = test_stash_tx_right
                    self.hgvs_genomic_possibilities.append(stash_genomic)
        except hgvs.exceptions.HGVSError as e:
            fn.exceptPass()
        # Intronic positions not supported. Will cause a Value Error
        except ValueError:
            fn.exceptPass()

        # Then to the left
        hgvs_stash = copy.deepcopy(hgvs_coding)
        try:
            hgvs_stash = self.variant.no_norm_evm.c_to_n(hgvs_stash)
        except:
            fn.exceptPass()
        try:
            stash_ac = hgvs_stash.ac
            stash_dict = vvHGVS.hard_left_hgvs2vcf(hgvs_stash, self.variant.primary_assembly,
                                                   self.variant.reverse_normalizer, self.validator.sf)
            stash_pos = int(stash_dict['pos'])
            stash_ref = stash_dict['ref']
            stash_alt = stash_dict['alt']
            # Generate an end position
            stash_end = str(stash_pos + len(stash_ref) - 1)
            # make a not real deletion insertion
            stash_hgvs_not_delins = self.validator.hp.parse_hgvs_variant(
                stash_ac + ':' + hgvs_stash.type + '.' + str(
                    stash_pos) + '_' + stash_end + 'del' + stash_ref + 'ins' + stash_alt)
            try:
                stash_hgvs_not_delins = self.variant.no_norm_evm.n_to_c(stash_hgvs_not_delins)
            except:
                fn.exceptPass()
                # Store a tx copy for later use
            test_stash_tx_left = copy.deepcopy(stash_hgvs_not_delins)
            # stash_genomic = vm.t_to_g(test_stash_tx_left, hgvs_genomic.ac)
            stash_genomic = self.validator.myvm_t_to_g(test_stash_tx_left, hgvs_genomic.ac, self.variant.no_norm_evm,
                                                       self.variant.hn)
            # Stash the outputs if required
            # test variants = NC_000006.11:g.90403795G= (causes double identity)
            #                 NC_000002.11:g.73675227_73675228insCTC
            #                 NC_000003.11:g.14561629_14561630GC= NC_000003.11:g.14561629_14561630insG (Odd gap position)
            # if test_stash_tx_left.posedit.edit.type == 'identity' and stash_genomic.posedit.edit.type == 'identity':
            # pass
            # len(stash_genomic.posedit.edit.ref):
            if len(test_stash_tx_left.posedit.edit.ref) == ((stash_genomic.posedit.pos.end.base -
                                                             stash_genomic.posedit.pos.start.base) + 1):
                if hasattr(test_stash_tx_left.posedit.edit,
                           'alt') and test_stash_tx_left.posedit.edit.alt is not None:
                    alt = test_stash_tx_left.posedit.edit.alt
                else:
                    alt = ''
                if hasattr(stash_genomic.posedit.edit,
                           'alt') and stash_genomic.posedit.edit.alt is not None:
                    g_alt = stash_genomic.posedit.edit.alt
                else:
                    g_alt = ''

                if (len(alt) - (
                        test_stash_tx_left.posedit.pos.end.base - test_stash_tx_left.posedit.pos.start.base) + 1) != (
                        len(g_alt) - (
                        stash_genomic.posedit.pos.end.base - stash_genomic.posedit.pos.start.base) + 1):
                    self.hgvs_genomic_possibilities.append(stash_genomic)
                else:
                    self.hgvs_genomic_possibilities.append('')
            elif test_stash_tx_left.posedit.edit.type == 'identity':
                reform_ident = str(test_stash_tx_left).split(':')[0]
                reform_ident = reform_ident + ':c.' + str(test_stash_tx_left.posedit.pos) + 'del' + str(
                    test_stash_tx_left.posedit.edit.ref)  # + 'ins' + str(test_stash_tx_left.posedit.edit.alt)
                hgvs_reform_ident = self.validator.hp.parse_hgvs_variant(reform_ident)
                try:
                    self.variant.hn.normalize(hgvs_reform_ident)
                except hgvs.exceptions.HGVSError as e:
                    error = str(e)
                    if re.search('spanning the exon-intron boundary', error):
                        stash_tx_left = test_stash_tx_left
                        self.hgvs_genomic_possibilities.append('')
                else:
                    stash_tx_left = test_stash_tx_left
                    self.hgvs_genomic_possibilities.append(stash_genomic)
            else:
                try:
                    self.variant.hn.normalize(test_stash_tx_left)
                except hgvs.exceptions.HGVSUnsupportedOperationError:
                    self.hgvs_genomic_possibilities.append('')
                else:
                    stash_tx_left = test_stash_tx_left
                    self.hgvs_genomic_possibilities.append(stash_genomic)
        except hgvs.exceptions.HGVSError as e:
            fn.exceptPass()
        except ValueError:
            fn.exceptPass()

        # direct mapping from reverse_normalized transcript insertions in the delins format
        self.rev_norm_ins(hgvs_coding, hgvs_genomic)

        logger.info('\nGENOMIC POSSIBILITIES')
        for possibility in self.hgvs_genomic_possibilities:
            if possibility == '':
                logger.info('X')
            else:
                logger.info(fn.valstr(possibility))

        logger.info('\n')

        # Set variables for problem specific warnings
        self.gapped_transcripts = ''
        self.auto_info = ''

        # Mark as not disparity detected
        self.disparity_deletion_in = ['false', 'false']

        # Loop through to see if a gap can be located
        # Set the variables required for corrective normalization
        possibility_counter = 0
        suppress_c_normalization = 'false'  # Applies to boundary crossing normalization

        # Copy a version of hgvs_genomic_possibilities
        for possibility in self.hgvs_genomic_possibilities:
            possibility_counter = possibility_counter + 1

            # Loop out stash possibilities which will not spot gaps so are empty
            if possibility == '':
                continue

            # Use VCF generation code to push hgvs_genomic as for 5 prime as possible to uncover gaps
            hgvs_genomic_variant = copy.deepcopy(possibility)
            reverse_normalized_hgvs_genomic = ''
            # Reverse normalize hgvs_genomic_variant: NOTE will replace ref
            try:
                reverse_normalized_hgvs_genomic = self.variant.reverse_normalizer.normalize(hgvs_genomic_variant)
            except hgvs.exceptions.HGVSError as e:
                # Strange error caused by gap in genomic
                error = str(e)
                if 'base start position must be <= end position' in error:
                    if hgvs_genomic.posedit.edit.type == 'delins':
                        start = hgvs_genomic.posedit.pos.start.base
                        end = hgvs_genomic.posedit.pos.end.base
                        lhb = self.validator.sf.fetch_seq(str(hgvs_genomic.ac), end - 1, end)
                        rhb = self.validator.sf.fetch_seq(str(hgvs_genomic.ac), start - 1, start)
                        hgvs_genomic.posedit.edit.ref = lhb + rhb
                        hgvs_genomic.posedit.edit.alt = lhb + hgvs_genomic.posedit.edit.alt + rhb
                        hgvs_genomic.posedit.pos.start.base = end
                        hgvs_genomic.posedit.pos.end.base = start
                        reverse_normalized_hgvs_genomic = self.variant.reverse_normalizer.normalize(hgvs_genomic)
                    if hgvs_genomic.posedit.edit.type == 'del':
                        start = hgvs_genomic.posedit.pos.start.base
                        end = hgvs_genomic.posedit.pos.end.base
                        lhb = self.validator.sf.fetch_seq(str(hgvs_genomic.ac), end - 1, end)
                        rhb = self.validator.sf.fetch_seq(str(hgvs_genomic.ac), start - 1, start)
                        hgvs_genomic.posedit.edit.ref = lhb + rhb
                        hgvs_genomic.posedit.edit.alt = lhb + rhb
                        hgvs_genomic.posedit.pos.start.base = end
                        hgvs_genomic.posedit.pos.end.base = start
                        reverse_normalized_hgvs_genomic = self.variant.reverse_normalizer.normalize(hgvs_genomic)
                if 'insertion length must be 1' in error:
                    if hgvs_genomic.posedit.edit.type == 'ins':
                        start = hgvs_genomic.posedit.pos.start.base
                        end = hgvs_genomic.posedit.pos.end.base
                        lhb = self.validator.sf.fetch_seq(str(hgvs_genomic.ac), start - 1, start)
                        rhb = self.validator.sf.fetch_seq(str(hgvs_genomic.ac), start, end)
                        hgvs_genomic.posedit.edit.ref = lhb + rhb
                        hgvs_genomic.posedit.edit.alt = lhb + hgvs_genomic.posedit.edit.alt + rhb
                        reverse_normalized_hgvs_genomic = self.variant.reverse_normalizer.normalize(hgvs_genomic)

            self.hgvs_genomic_5pr = copy.deepcopy(reverse_normalized_hgvs_genomic)

            # Create VCF
            vcf_dict = vvHGVS.hgvs2vcf(reverse_normalized_hgvs_genomic, self.variant.primary_assembly,
                                       self.variant.reverse_normalizer, self.validator.sf)
            pos = vcf_dict['pos']
            ref = vcf_dict['ref']
            alt = vcf_dict['alt']

            # Generate an end position
            end = str(int(pos) + len(ref) - 1)
            pos = str(pos)

            # Store a not real deletion insertion to test for gapping
            stored_hgvs_not_delins = self.validator.hp.parse_hgvs_variant(str(self.hgvs_genomic_5pr.ac) + ':' +
                self.hgvs_genomic_5pr.type + '.' + pos + '_' + end + 'del' + ref + 'ins' + alt)

            # Detect intronic variation using normalization
            intronic_variant = 'false'

            # Save a copy of current hgvs_coding
            try:
                saved_hgvs_coding = self.variant.no_norm_evm.g_to_t(stored_hgvs_not_delins, hgvs_coding.ac)
            except hgvs.exceptions.HGVSInvalidIntervalError as e:
                if str(e) == 'start or end or both are beyond the bounds of transcript record':
                    continue
                else:
                    saved_hgvs_coding = self.variant.no_norm_evm.g_to_n(reverse_normalized_hgvs_genomic,
                                                                   hgvs_coding.ac)

            # Look for normalized variant options that do not match hgvs_coding
            hgvs_seek_var = self.get_hgvs_seek_var(hgvs_genomic, hgvs_coding)

            if (
                    hgvs_seek_var.posedit.pos.start.base + hgvs_seek_var.posedit.pos.start.offset) > (
                    hgvs_coding.posedit.pos.start.base + hgvs_coding.posedit.pos.start.offset) and (
                    hgvs_seek_var.posedit.pos.end.base + hgvs_seek_var.posedit.pos.end.offset) > (
                    hgvs_coding.posedit.pos.end.base + hgvs_coding.posedit.pos.end.offset) and rec_var != 'false':
                pass
            else:
                hgvs_seek_var = saved_hgvs_coding

            try:
                self.variant.hn.normalize(hgvs_seek_var)
            except hgvs.exceptions.HGVSUnsupportedOperationError as e:
                error = str(e)
                if 'Normalization of intronic variants is not supported' in error or \
                        'Unsupported normalization of variants spanning the exon-intron boundary' in error:
                    if 'Unsupported normalization of variants spanning the exon-intron boundary' in error:
                        intronic_variant = 'hard_fail'
                    else:
                        # Double check to see whether the variant is actually intronic?
                        for exon in ori:
                            genomic_start = int(exon['alt_start_i'])
                            genomic_end = int(exon['alt_end_i'])
                            if (genomic_start < self.hgvs_genomic_5pr.posedit.pos.start.base <= genomic_end) and (
                                    genomic_start < self.hgvs_genomic_5pr.posedit.pos.end.base <= genomic_end):
                                intronic_variant = 'false'
                                break
                            else:
                                intronic_variant = 'true'

            if intronic_variant != 'hard_fail':
                if re.search(r'\d+\+', str(hgvs_seek_var.posedit.pos)) or re.search(r'\d+-', str(
                        hgvs_seek_var.posedit.pos)) or re.search(r'\*\d+\+', str(
                        hgvs_seek_var.posedit.pos)) or re.search(r'\*\d+-', str(hgvs_seek_var.posedit.pos)):
                    # Double check to see whether the variant is actually intronic?
                    for exon in ori:
                        genomic_start = int(exon['alt_start_i'])
                        genomic_end = int(exon['alt_end_i'])
                        if (genomic_start < self.hgvs_genomic_5pr.posedit.pos.start.base <= genomic_end) and (
                                genomic_start < self.hgvs_genomic_5pr.posedit.pos.end.base <= genomic_end):
                            intronic_variant = 'false'
                            break
                        else:
                            intronic_variant = 'true'

            if re.search(r'\d+\+', str(hgvs_seek_var.posedit.pos)) or re.search(r'\d+-', str(
                    hgvs_seek_var.posedit.pos)) or re.search(r'\*\d+\+', str(
                    hgvs_seek_var.posedit.pos)) or re.search(r'\*\d+-', str(hgvs_seek_var.posedit.pos)):
                # Double check to see whether the variant is actually intronic?
                for exon in ori:
                    genomic_start = int(exon['alt_start_i'])
                    genomic_end = int(exon['alt_end_i'])
                    if (genomic_start < self.hgvs_genomic_5pr.posedit.pos.start.base <= genomic_end) and (
                            genomic_start < self.hgvs_genomic_5pr.posedit.pos.end.base <= genomic_end):
                        intronic_variant = 'false'
                        break
                    else:
                        intronic_variant = 'true'

            if intronic_variant != 'true':
                # Flag RefSeqGene for ammendment
                # amend_RefSeqGene = 'false'
                # Attempt to find gaps in reference sequence by catching disparity in genome length and overlapping transcript lengths
                hgvs_not_delins = ''
                if stored_hgvs_not_delins != '':
                    # Refresh hgvs_not_delins from stored_hgvs_not_delins
                    hgvs_not_delins = self.dup_ins_5prime_shift(stored_hgvs_not_delins, saved_hgvs_coding)

                    try:
                        self.tx_hgvs_not_delins = self.variant.no_norm_evm.g_to_n(hgvs_not_delins,
                                                                                  saved_hgvs_coding.ac)
                    except hgvs.exceptions.HGVSInvalidIntervalError:
                        self.tx_hgvs_not_delins = self.variant.no_norm_evm.g_to_n(reverse_normalized_hgvs_genomic,
                                                                                  saved_hgvs_coding.ac)
                    # Create normalized version of tx_hgvs_not_delins
                    rn_tx_hgvs_not_delins = copy.deepcopy(self.tx_hgvs_not_delins)

                    # Check for +1 base and adjust
                    if '+' in str(rn_tx_hgvs_not_delins.posedit.pos.end) and '+' in str(
                            rn_tx_hgvs_not_delins.posedit.pos.start):
                        rn_tx_hgvs_not_delins = self.remove_offsetting_to_span_gap(rn_tx_hgvs_not_delins)

                    elif '+' in str(rn_tx_hgvs_not_delins.posedit.pos.end):
                        rn_tx_hgvs_not_delins, hgvs_not_delins = self.move_tx_end_base_to_next_nonoffset(
                            rn_tx_hgvs_not_delins, saved_hgvs_coding, back=False)

                    elif '+' in str(rn_tx_hgvs_not_delins.posedit.pos.start):
                        rn_tx_hgvs_not_delins, hgvs_not_delins = self.move_tx_start_base_to_previous_nonoffset(
                            rn_tx_hgvs_not_delins, saved_hgvs_coding)

                    # Check for -ve base and adjust
                    elif '-' in str(rn_tx_hgvs_not_delins.posedit.pos.end) and '-' in str(
                            rn_tx_hgvs_not_delins.posedit.pos.start):
                        rn_tx_hgvs_not_delins = self.remove_offsetting_to_span_gap(rn_tx_hgvs_not_delins)

                    elif '-' in str(rn_tx_hgvs_not_delins.posedit.pos.end):
                        rn_tx_hgvs_not_delins, hgvs_not_delins = self.move_tx_end_base_to_next_nonoffset(
                            rn_tx_hgvs_not_delins, saved_hgvs_coding)

                    elif '-' in str(rn_tx_hgvs_not_delins.posedit.pos.start):
                        rn_tx_hgvs_not_delins, hgvs_not_delins = self.move_tx_start_base_to_previous_nonoffset(
                            rn_tx_hgvs_not_delins, saved_hgvs_coding, with_base_subtract=True)

                    # Logic
                    hgvs_not_delins = self.logic_check(hgvs_not_delins, rn_tx_hgvs_not_delins, hgvs_coding)

                # 'At hgvs_genomic'
                # Final sanity checks
                try:
                    self.validator.vm.g_to_t(hgvs_not_delins, self.tx_hgvs_not_delins.ac)
                except Exception as e:
                    if str(e) == 'start or end or both are beyond the bounds of transcript record':
                        continue
                try:
                    self.variant.hn.normalize(self.tx_hgvs_not_delins)
                except hgvs.exceptions.HGVSUnsupportedOperationError as e:
                    error = str(e)
                    if 'Normalization of intronic variants is not supported' in error or \
                            'Unsupported normalization of variants spanning the exon-intron boundary' in error:
                        if 'Unsupported normalization of variants spanning the exon-intron boundary' in error:
                            continue
                        elif 'Normalization of intronic variants is not supported' in error:
                            # We know that this cannot be because of an intronic variant, so must be aligned to tx gap
                            self.disparity_deletion_in = ['transcript', 'Requires Analysis']

                # amend_RefSeqGene = 'false'
                # Recreate hgvs_genomic
                if self.disparity_deletion_in[0] == 'transcript':
                    hgvs_genomic = hgvs_not_delins

                # Find oddly placed gaps where the tx variant is encompassed in the gap
                if self.disparity_deletion_in[0] == 'false' and (possibility_counter == 3 or possibility_counter == 4):
                    rg = self.variant.reverse_normalizer.normalize(hgvs_not_delins)
                    rtx = self.validator.vm.g_to_t(rg, self.tx_hgvs_not_delins.ac)
                    fg = self.variant.hn.normalize(hgvs_not_delins)
                    ftx = self.validator.vm.g_to_t(fg, self.tx_hgvs_not_delins.ac)
                    if (rtx.posedit.pos.start.offset == 0 and rtx.posedit.pos.end.offset == 0) and (
                            ftx.posedit.pos.start.offset != 0 and ftx.posedit.pos.end.offset != 0):
                        exons = self.validator.hdp.get_tx_exons(ftx.ac, hgvs_not_delins.ac,
                                                                self.validator.alt_aln_method)
                        exonic = False
                        for ex_test in exons:
                            if ftx.posedit.pos.start.base in range(ex_test[6], ex_test[
                                    7]) and ftx.posedit.pos.end.base in range(ex_test[6], ex_test[7]):
                                exonic = True
                        if exonic is True:
                            hgvs_not_delins = fg
                            hgvs_genomic = fg
                            self.hgvs_genomic_5pr = fg
                            try:
                                self.tx_hgvs_not_delins = self.validator.vm.c_to_n(ftx)
                            except Exception:
                                self.tx_hgvs_not_delins = ftx
                            self.disparity_deletion_in = ['transcript', 'Requires Analysis']

                # Pre-processing of self.tx_hgvs_not_delins
                try:
                    if self.tx_hgvs_not_delins.posedit.edit.alt is None:
                        self.tx_hgvs_not_delins.posedit.edit.alt = ''
                except Exception as e:
                    if str(e) == "'Dup' object has no attribute 'alt'":
                        tx_hgvs_not_delins_delins_from_dup = fn.hgvs_dup2indel(self.tx_hgvs_not_delins)
                        self.tx_hgvs_not_delins = self.validator.hp.parse_hgvs_variant(
                            tx_hgvs_not_delins_delins_from_dup)

                # GAP IN THE TRANSCRIPT DISPARITY DETECTED
                if self.disparity_deletion_in[0] == 'transcript':
                    # Suppress intron boundary crossing due to non-intron intron based c. seq annotations
                    suppress_c_normalization = 'true'
                    # amend_RefSeqGene = 'true'
                    # ANY VARIANT WHOLLY WITHIN THE GAP
                    hgvs_refreshed_variant = self.transcript_disparity(reverse_normalized_hgvs_genomic,
                                                                       stored_hgvs_not_delins, hgvs_genomic, 2)

                # GAP IN THE CHROMOSOME
                elif self.disparity_deletion_in[0] == 'chromosome':
                    suppress_c_normalization = 'true'
                    # amend_RefSeqGene = 'true'
                    if possibility_counter == 3:
                        hgvs_refreshed_variant = stash_tx_right
                    elif possibility_counter == 4:
                        hgvs_refreshed_variant = stash_tx_left
                    else:
                        hgvs_refreshed_variant = chromosome_normalized_hgvs_coding
                    # Warn
                    self.auto_info = self.auto_info + str(hgvs_refreshed_variant.ac) + ':c.' + str(
                        hgvs_refreshed_variant.posedit.pos) + ' contains ' + str(self.disparity_deletion_in[
                            1]) + ' transcript base(s) that fail to align to chromosome ' + str(
                        hgvs_genomic.ac) + '\n'
                else:
                    # Keep the same by re-setting rel_var
                    hgvs_refreshed_variant = hgvs_coding
                # amend_RefSeqGene = 'false'

                # Edit the output
                if 'NM_' in str(hgvs_refreshed_variant.ac) and not 'c' in str(hgvs_refreshed_variant.type):
                    hgvs_refreshed_variant = self.variant.no_norm_evm.n_to_c(hgvs_refreshed_variant)

                try:
                    self.variant.hn.normalize(hgvs_refreshed_variant)
                except Exception as e:
                    error = str(e)

                    # Ensure the final variant is not intronic nor does it cross exon boundaries
                    if 'Normalization of intronic variants is not supported' in error or \
                            'Unsupported normalization of variants spanning the exon-intron boundary' in error:
                        hgvs_refreshed_variant = saved_hgvs_coding
                    else:
                        logger.warning(error)
                        continue

                # Quick check to make sure the coding variant has not changed
                try:
                    to_test = self.variant.hn.normalize(hgvs_refreshed_variant)
                except:
                    to_test = hgvs_refreshed_variant
                if str(to_test.posedit.edit) != str(hgvs_coding.posedit.edit):
                    # Try the next available genomic option
                    if hgvs_coding.posedit.edit.type == 'identity' and to_test.posedit.edit.type == 'identity':
                        hgvs_coding = to_test
                    else:
                        continue
                # Update hgvs_genomic
                hgvs_genomic = self.validator.myvm_t_to_g(hgvs_refreshed_variant, hgvs_genomic.ac,
                                                          self.variant.no_norm_evm, self.variant.hn)
                if hgvs_genomic.posedit.edit.type == 'identity':
                    re_c = self.validator.vm.g_to_t(hgvs_genomic, hgvs_refreshed_variant.ac)
                    if (self.variant.hn.normalize(re_c)) != (self.variant.hn.normalize(hgvs_refreshed_variant)):
                        shuffle_left_g = copy.copy(hgvs_genomic)
                        shuffle_left_g.posedit.edit.ref = ''
                        shuffle_left_g.posedit.edit.alt = ''
                        shuffle_left_g.posedit.pos.start.base = shuffle_left_g.posedit.pos.start.base - 1
                        shuffle_left_g.posedit.pos.end.base = shuffle_left_g.posedit.pos.end.base - 1
                        shuffle_left_g = self.variant.reverse_normalizer.normalize(shuffle_left_g)
                        re_c = self.validator.vm.g_to_t(shuffle_left_g, hgvs_refreshed_variant.ac)
                        if (self.variant.hn.normalize(re_c)) != (self.variant.hn.normalize(hgvs_refreshed_variant)):
                            hgvs_genomic = shuffle_left_g

            # Break if gap has been detected
            if self.disparity_deletion_in[0] != 'false':
                break

        # Warn user about gapping
        if self.auto_info != '':
            info_lines = self.auto_info.split('\n')
            info_keys = {}
            for information in info_lines:
                info_keys[information] = ''
            info_out = []
            info_out.append('The displayed variants may be artefacts of aligning ' + hgvs_coding.ac + ' with genome '
                            'build ' + self.variant.primary_assembly)
            for ky in list(info_keys.keys()):
                info_out.append(ky)
            self.auto_info = '\n'.join(info_out)
            self.auto_info = self.auto_info + '\nCaution should be used when reporting the displayed variant ' \
                                              'descriptions: If you are unsure, please contact admin'
            self.auto_info = self.auto_info.replace('\n', ': ')
            self.variant.warnings.append(self.auto_info)
            logger.warning(self.auto_info)
        # Normailse hgvs_genomic
        try:
            hgvs_genomic = self.variant.hn.normalize(hgvs_genomic)
        except hgvs.exceptions.HGVSError as e:
            # Strange error caused by gap in genomic
            error = str(e)

            if 'base start position must be <= end position' in error and self.disparity_deletion_in[0] == 'chromosome':
                if hgvs_genomic.posedit.edit.type == 'delins':
                    start = hgvs_genomic.posedit.pos.start.base
                    end = hgvs_genomic.posedit.pos.end.base
                    lhb = self.validator.sf.fetch_seq(str(hgvs_genomic.ac), end - 1, end)
                    rhb = self.validator.sf.fetch_seq(str(hgvs_genomic.ac), start - 1, start)
                    hgvs_genomic.posedit.edit.ref = lhb + rhb
                    hgvs_genomic.posedit.edit.alt = lhb + hgvs_genomic.posedit.edit.alt + rhb
                    hgvs_genomic.posedit.pos.start.base = end
                    hgvs_genomic.posedit.pos.end.base = start
                    hgvs_genomic = self.variant.hn.normalize(hgvs_genomic)
                if hgvs_genomic.posedit.edit.type == 'del':
                    start = hgvs_genomic.posedit.pos.start.base
                    end = hgvs_genomic.posedit.pos.end.base
                    lhb = self.validator.sf.fetch_seq(str(hgvs_genomic.ac), end - 1, end)
                    rhb = self.validator.sf.fetch_seq(str(hgvs_genomic.ac), start - 1, start)
                    hgvs_genomic.posedit.edit.ref = lhb + rhb
                    hgvs_genomic.posedit.edit.alt = lhb + rhb
                    hgvs_genomic.posedit.pos.start.base = end
                    hgvs_genomic.posedit.pos.end.base = start
                    hgvs_genomic = self.variant.hn.normalize(hgvs_genomic)

        return hgvs_genomic, suppress_c_normalization, hgvs_coding

    def g_to_t_gapped_mapping_stage2(self, ori, hgvs_coding, hgvs_genomic):
        logger.warning('g_to_t gap code 2 active')

        hgvs_genomic_variant = hgvs_genomic
        reverse_normalized_hgvs_genomic = self.variant.reverse_normalizer.normalize(hgvs_genomic_variant)
        self.hgvs_genomic_5pr = copy.deepcopy(reverse_normalized_hgvs_genomic)
        vcf_dict = vvHGVS.hgvs2vcf(reverse_normalized_hgvs_genomic, self.variant.primary_assembly,
                                   self.variant.reverse_normalizer, self.validator.sf)
        chr = vcf_dict['chr']
        pos = vcf_dict['pos']
        ref = vcf_dict['ref']
        alt = vcf_dict['alt']

        # Create a VCF call
        vcf_component_list = [str(chr), str(pos), str(ref), (alt)]
        vcf_genomic = '-'.join(vcf_component_list)

        # DO NOT DELETE
        # Generate an end position
        end = str(int(pos) + len(ref) - 1)
        pos = str(pos)
        stored_hgvs_not_delins = self.validator.hp.parse_hgvs_variant(str(
            self.hgvs_genomic_5pr.ac) + ':' + self.hgvs_genomic_5pr.type + '.' + pos + '_' + end + 'del' + ref +
                                                                      'ins' + alt)
        self.orientation = int(ori[0]['alt_strand'])
        saved_hgvs_coding = copy.deepcopy(hgvs_coding)

        # is it in an exon?
        is_it_in_an_exon = 'no'
        for exon in ori:
            genomic_start = int(exon['alt_start_i'])
            genomic_end = int(exon['alt_end_i'])
            # Take from stored copy
            # hgvs_genomic_5pr = copy.deepcopy(stored_hgvs_genomic_5pr)
            if (genomic_start < self.hgvs_genomic_5pr.posedit.pos.start.base <= genomic_end) and (
                    genomic_start < self.hgvs_genomic_5pr.posedit.pos.end.base <= genomic_end):
                is_it_in_an_exon = 'yes'
        if is_it_in_an_exon == 'yes':
            # map form reverse normalized g. to c.
            # hgvs_from_5n_g = self.variant.no_norm_evm.g_to_t(self.hgvs_genomic_5pr, saved_hgvs_coding.ac)

            # Attempt to find gaps in reference sequence by catching disparity in genome length and
            # overlapping transcript lengths
            self.disparity_deletion_in = ['false', 'false']
            hgvs_not_delins = ''
            hard_fail = 'false'
            if stored_hgvs_not_delins != '':
                # Refresh hgvs_not_delins from stored_hgvs_not_delins
                hgvs_not_delins = self.dup_ins_5prime_shift(stored_hgvs_not_delins, saved_hgvs_coding)
                try:
                    self.tx_hgvs_not_delins = self.variant.no_norm_evm.g_to_n(hgvs_not_delins, saved_hgvs_coding.ac)
                except Exception as e:
                    if str(e) == 'start or end or both are beyond the bounds of transcript record':
                        self.tx_hgvs_not_delins = hgvs_coding
                        hard_fail = 'true'

                # Create normalized version of self.tx_hgvs_not_delins
                rn_tx_hgvs_not_delins = copy.deepcopy(self.tx_hgvs_not_delins)
                # Check for +ve base and adjust
                if '+' in str(rn_tx_hgvs_not_delins.posedit.pos.end) and '+' in \
                        str(rn_tx_hgvs_not_delins.posedit.pos.start):
                    rn_tx_hgvs_not_delins = self.remove_offsetting_to_span_gap(rn_tx_hgvs_not_delins)

                elif '+' in str(rn_tx_hgvs_not_delins.posedit.pos.end):
                    rn_tx_hgvs_not_delins, hgvs_not_delins = self.move_tx_end_base_to_next_nonoffset(
                        rn_tx_hgvs_not_delins, saved_hgvs_coding, back=False)

                elif '+' in str(rn_tx_hgvs_not_delins.posedit.pos.start):
                    rn_tx_hgvs_not_delins, hgvs_not_delins = self.move_tx_start_base_to_previous_nonoffset(
                        rn_tx_hgvs_not_delins, saved_hgvs_coding)

                # Check for -ve base and adjust
                elif '-' in str(rn_tx_hgvs_not_delins.posedit.pos.end) and '-' in str(
                        rn_tx_hgvs_not_delins.posedit.pos.start):
                    rn_tx_hgvs_not_delins = self.remove_offsetting_to_span_gap(rn_tx_hgvs_not_delins)

                elif '-' in str(rn_tx_hgvs_not_delins.posedit.pos.end):
                    rn_tx_hgvs_not_delins, hgvs_not_delins = self.move_tx_end_base_to_next_nonoffset(
                        rn_tx_hgvs_not_delins, saved_hgvs_coding)

                elif '-' in str(rn_tx_hgvs_not_delins.posedit.pos.start):
                    rn_tx_hgvs_not_delins, hgvs_not_delins = self.move_tx_start_base_to_previous_nonoffset(
                        rn_tx_hgvs_not_delins, saved_hgvs_coding, with_base_subtract=True)

                # Logic
                hgvs_not_delins = self.logic_check(hgvs_not_delins, rn_tx_hgvs_not_delins, hgvs_coding)

            # Final sanity checks
            try:
                self.validator.vm.g_to_t(hgvs_not_delins, self.tx_hgvs_not_delins.ac)
            except Exception as e:
                if str(e) == 'start or end or both are beyond the bounds of transcript record':
                    logger.warning(str(e))
                    return True
            try:
                self.variant.hn.normalize(self.tx_hgvs_not_delins)
            except hgvs.exceptions.HGVSUnsupportedOperationError as e:
                error = str(e)
                if 'Normalization of intronic variants is not supported' in error or \
                        'Unsupported normalization of variants spanning the exon-intron boundary' in error:
                    if 'Unsupported normalization of variants spanning the exon-intron boundary' in error:
                        logger.warning(error)
                        return True
                    elif 'Normalization of intronic variants is not supported' in error:
                        # We know that this cannot be because of an intronic variant, so must be aligned to tx gap
                        self.disparity_deletion_in = ['transcript', 'Requires Analysis']

            if hard_fail == 'true':
                self.disparity_deletion_in = ['false', 'false']

            # Recreate hgvs_genomic
            if self.disparity_deletion_in[0] == 'transcript':
                hgvs_genomic = hgvs_not_delins

            # Pre-processing of tx_hgvs_not_delins
            try:
                if self.tx_hgvs_not_delins.posedit.edit.alt is None:
                    self.tx_hgvs_not_delins.posedit.edit.alt = ''
            except Exception as e:
                if str(e) == "'Dup' object has no attribute 'alt'":
                    tx_hgvs_not_delins_delins_from_dup = fn.hgvs_dup2indel(self.tx_hgvs_not_delins)
                    self.tx_hgvs_not_delins = self.validator.hp.parse_hgvs_variant(tx_hgvs_not_delins_delins_from_dup)

            # GAP IN THE TRANSCRIPT DISPARITY DETECTED
            if self.disparity_deletion_in[0] == 'transcript':
                # ANY VARIANT WHOLLY WITHIN THE GAP
                hgvs_refreshed_variant = self.transcript_disparity(reverse_normalized_hgvs_genomic,
                                                                   stored_hgvs_not_delins, hgvs_genomic, 3)

            # GAP IN THE CHROMOSOME
            elif self.disparity_deletion_in[0] == 'chromosome':
                hgvs_refreshed_variant = self.tx_hgvs_not_delins
                # Warn
                self.auto_info = self.auto_info + str(hgvs_refreshed_variant.ac) + ':c.' + str(
                    hgvs_refreshed_variant.posedit.pos) + ' contains ' + str(self.disparity_deletion_in[1]) + \
                    ' transcript base(s) that fail to align to chromosome ' + str(hgvs_genomic.ac) + '\n'
                self.gapped_transcripts = self.gapped_transcripts + str(hgvs_refreshed_variant.ac) + ' '
            else:
                # Keep the same by re-setting rel_var
                hgvs_refreshed_variant = saved_hgvs_coding

            # Edit the output
            hgvs_refreshed_variant = self.edit_output(hgvs_refreshed_variant, saved_hgvs_coding)

            # Sort out equality to equality c. events where the code will add 2 additional bases
            if hgvs_coding.posedit.edit.type == 'identity' and hgvs_refreshed_variant.posedit.edit.type == 'identity':
                pass
            else:
                hgvs_coding = copy.deepcopy(hgvs_refreshed_variant)

        return hgvs_coding

    def g_to_t_gap_compensation_version3(self, hgvs_alt_genomic, hgvs_coding, ori, alt_chr, rec_var):

        self.orientation = int(ori[0]['alt_strand'])
        hgvs_genomic = copy.deepcopy(hgvs_alt_genomic)

        logger.warning('g_to_t gap code 3 active')
        rn_hgvs_genomic = self.variant.reverse_normalizer.normalize(hgvs_alt_genomic)
        self.hgvs_genomic_possibilities.append(rn_hgvs_genomic)
        if self.orientation != -1:
            try:
                chromosome_normalized_hgvs_coding = self.variant.reverse_normalizer.normalize(
                    hgvs_coding)
            except hgvs.exceptions.HGVSUnsupportedOperationError:
                chromosome_normalized_hgvs_coding = hgvs_coding
        else:
            try:
                chromosome_normalized_hgvs_coding = self.variant.hn.normalize(hgvs_coding)
            except hgvs.exceptions.HGVSUnsupportedOperationError:
                chromosome_normalized_hgvs_coding = hgvs_coding

        most_3pr_hgvs_genomic = self.validator.myvm_t_to_g(chromosome_normalized_hgvs_coding, alt_chr,
                                                           self.variant.no_norm_evm, self.variant.hn)
        self.hgvs_genomic_possibilities.append(most_3pr_hgvs_genomic)

        # First to the right
        hgvs_stash = copy.deepcopy(hgvs_coding)
        stash_tx_right = ''
        stash_tx_left = ''
        try:
            hgvs_stash = self.variant.no_norm_evm.c_to_n(hgvs_stash)
        except:
            fn.exceptPass()
        try:
            stash_ac = hgvs_stash.ac
            stash_dict = vvHGVS.hard_right_hgvs2vcf(hgvs_stash, self.variant.primary_assembly, self.variant.hn,
                                                    self.validator.sf)
            stash_pos = int(stash_dict['pos'])
            stash_ref = stash_dict['ref']
            stash_alt = stash_dict['alt']
            # Generate an end position
            stash_end = str(stash_pos + len(stash_ref) - 1)
            # make a not real deletion insertion
            stash_hgvs_not_delins = self.validator.hp.parse_hgvs_variant(
                stash_ac + ':' + hgvs_stash.type + '.' + str(
                    stash_pos) + '_' + stash_end + 'del' + stash_ref + 'ins' + stash_alt)
            try:
                stash_hgvs_not_delins = self.variant.no_norm_evm.n_to_c(stash_hgvs_not_delins)
            except:
                fn.exceptPass()
                # Store a tx copy for later use
            test_stash_tx_right = copy.deepcopy(stash_hgvs_not_delins)
            stash_genomic = self.validator.myvm_t_to_g(test_stash_tx_right, hgvs_alt_genomic.ac,
                                                       self.variant.no_norm_evm, self.variant.hn)
            # Stash the outputs if required
            # test variants = NC_000006.11:g.90403795G= (causes double identity)
            #                 NC_000002.11:g.73675227_73675228insCTC (? incorrect assumed insertion position)
            #                 NC_000003.11:g.14561629_14561630GC= NC_000003.11:g.14561629_14561630insG (Odd gap position
            # if test_stash_tx_right.posedit.edit.type == 'identity' and stash_genomic.posedit.edit.type == 'identity':
            # pass
            if len(test_stash_tx_right.posedit.edit.ref) == ((stash_genomic.posedit.pos.end.base -
                                                              stash_genomic.posedit.pos.start.base) + 1):
                stash_tx_right = test_stash_tx_right
                if hasattr(test_stash_tx_right.posedit.edit,
                           'alt') and test_stash_tx_right.posedit.edit.alt is not None:
                    alt = test_stash_tx_right.posedit.edit.alt
                else:
                    alt = ''
                if hasattr(stash_genomic.posedit.edit,
                           'alt') and stash_genomic.posedit.edit.alt is not None:
                    g_alt = stash_genomic.posedit.edit.alt
                else:
                    g_alt = ''
                if (len(alt) - (
                        test_stash_tx_right.posedit.pos.end.base - test_stash_tx_right.posedit.pos.start.base) + 1) != (
                        len(g_alt) - (
                        stash_genomic.posedit.pos.end.base - stash_genomic.posedit.pos.start.base) + 1):
                    self.hgvs_genomic_possibilities.append(stash_genomic)
                else:
                    self.hgvs_genomic_possibilities.append('')
            elif test_stash_tx_right.posedit.edit.type == 'identity':
                reform_ident = str(test_stash_tx_right).split(':')[0]
                reform_ident = reform_ident + ':c.' + str(test_stash_tx_right.posedit.pos) + 'del' + str(
                    test_stash_tx_right.posedit.edit.ref)  # + 'ins' + str(test_stash_tx_right.posedit.edit.alt)
                hgvs_reform_ident = self.validator.hp.parse_hgvs_variant(reform_ident)
                try:
                    self.variant.hn.normalize(hgvs_reform_ident)
                except hgvs.exceptions.HGVSError as e:
                    error = str(e)
                    if 'spanning the exon-intron boundary' in error:
                        stash_tx_right = test_stash_tx_right
                        self.hgvs_genomic_possibilities.append('')
                else:
                    stash_tx_right = test_stash_tx_right
                    self.hgvs_genomic_possibilities.append(stash_genomic)
            else:
                try:
                    self.variant.hn.normalize(test_stash_tx_right)
                except hgvs.exceptions.HGVSUnsupportedOperationError:
                    self.hgvs_genomic_possibilities.append('')
                else:
                    stash_tx_right = test_stash_tx_right
                    self.hgvs_genomic_possibilities.append(stash_genomic)
        except hgvs.exceptions.HGVSError:
            fn.exceptPass()
        except ValueError:
            fn.exceptPass()

        # Then to the left
        hgvs_stash = copy.deepcopy(hgvs_coding)
        try:
            hgvs_stash = self.variant.no_norm_evm.c_to_n(hgvs_stash)
        except:
            fn.exceptPass()
        try:
            stash_ac = hgvs_stash.ac
            stash_dict = vvHGVS.hard_left_hgvs2vcf(hgvs_stash, self.variant.primary_assembly,
                                                   self.variant.reverse_normalizer, self.validator.sf)
            stash_pos = int(stash_dict['pos'])
            stash_ref = stash_dict['ref']
            stash_alt = stash_dict['alt']
            # Generate an end position
            stash_end = str(stash_pos + len(stash_ref) - 1)
            # make a not real deletion insertion
            stash_hgvs_not_delins = self.validator.hp.parse_hgvs_variant(
                stash_ac + ':' + hgvs_stash.type + '.' + str(
                    stash_pos) + '_' + stash_end + 'del' + stash_ref + 'ins' + stash_alt)
            try:
                stash_hgvs_not_delins = self.variant.no_norm_evm.n_to_c(stash_hgvs_not_delins)
            except:
                fn.exceptPass()
                # Store a tx copy for later use
            test_stash_tx_left = copy.deepcopy(stash_hgvs_not_delins)
            stash_genomic = self.validator.myvm_t_to_g(test_stash_tx_left, hgvs_alt_genomic.ac,
                                                  self.variant.no_norm_evm, self.variant.hn)
            # Stash the outputs if required
            # test variants = NC_000006.11:g.90403795G= (causes double identity)
            #                 NC_000002.11:g.73675227_73675228insCTC
            #                 NC_000003.11:g.14561629_14561630GC= NC_000003.11:g.14561629_14561630insG (Odd gap position
            # if test_stash_tx_left.posedit.edit.type == 'identity' and stash_genomic.posedit.edit.type == 'identity':
            # pass
            if len(test_stash_tx_left.posedit.edit.ref) == ((stash_genomic.posedit.pos.end.base -
                                                             stash_genomic.posedit.pos.start.base) + 1):
                stash_tx_left = test_stash_tx_left
                if hasattr(test_stash_tx_left.posedit.edit,
                           'alt') and test_stash_tx_left.posedit.edit.alt is not None:
                    alt = test_stash_tx_left.posedit.edit.alt
                else:
                    alt = ''
                if hasattr(stash_genomic.posedit.edit,
                           'alt') and stash_genomic.posedit.edit.alt is not None:
                    g_alt = stash_genomic.posedit.edit.alt
                else:
                    g_alt = ''
                if (len(alt) - (
                        test_stash_tx_left.posedit.pos.end.base - test_stash_tx_left.posedit.pos.start.base) + 1) != (
                        len(g_alt) - (
                        stash_genomic.posedit.pos.end.base - stash_genomic.posedit.pos.start.base) + 1):
                    self.hgvs_genomic_possibilities.append(stash_genomic)
                else:
                    self.hgvs_genomic_possibilities.append('')
            elif test_stash_tx_left.posedit.edit.type == 'identity':
                reform_ident = str(test_stash_tx_left).split(':')[0]
                reform_ident = reform_ident + ':c.' + str(test_stash_tx_left.posedit.pos) + 'del' + str(
                    test_stash_tx_left.posedit.edit.ref)  # + 'ins' + str(test_stash_tx_left.posedit.edit.alt)
                hgvs_reform_ident = self.validator.hp.parse_hgvs_variant(reform_ident)
                try:
                    self.variant.hn.normalize(hgvs_reform_ident)
                except hgvs.exceptions.HGVSError as e:
                    error = str(e)
                    if 'spanning the exon-intron boundary' in error:
                        stash_tx_left = test_stash_tx_left
                        self.hgvs_genomic_possibilities.append('')
                else:
                    stash_tx_left = test_stash_tx_left
                    self.hgvs_genomic_possibilities.append(stash_genomic)
            else:
                try:
                    self.variant.hn.normalize(test_stash_tx_left)
                except hgvs.exceptions.HGVSUnsupportedOperationError:
                    self.hgvs_genomic_possibilities.append('')
                else:
                    stash_tx_left = test_stash_tx_left
                    self.hgvs_genomic_possibilities.append(stash_genomic)
        except hgvs.exceptions.HGVSError as e:
            fn.exceptPass()
        except ValueError:
            fn.exceptPass()

        # direct mapping from reverse_normalized transcript insertions in the delins format
        self.rev_norm_ins(hgvs_coding, hgvs_genomic)

        # Set variables for problem specific warnings
        self.gapped_transcripts = ''
        self.auto_info = ''

        # Mark as not disparity detected
        self.disparity_deletion_in = ['false', 'false']
        # Loop through to see if a gap can be located
        possibility_counter = 0
        for possibility in self.hgvs_genomic_possibilities:
            possibility_counter = possibility_counter + 1
            # Loop out stash possibilities which will not spot gaps so are empty
            if possibility == '':
                continue

            # Use VCF generation code to push hgvs_genomic as for 5 prime as possible to uncover gaps
            hgvs_genomic_variant = possibility
            reverse_normalized_hgvs_genomic = ''

            # Reverse normalize hgvs_genomic_variant: NOTE will replace ref
            try:
                reverse_normalized_hgvs_genomic = self.variant.reverse_normalizer.normalize(
                    hgvs_genomic_variant)
            except hgvs.exceptions.HGVSError as e:
                # Strange error caused by gap in genomic
                error = str(e)
                if 'base start position must be <= end position' in error:
                    if hgvs_genomic.posedit.edit.type == 'delins':
                        start = hgvs_genomic.posedit.pos.start.base
                        end = hgvs_genomic.posedit.pos.end.base
                        lhb = self.validator.sf.fetch_seq(str(hgvs_genomic.ac), end - 1, end)
                        rhb = self.validator.sf.fetch_seq(str(hgvs_genomic.ac), start - 1, start)
                        hgvs_genomic.posedit.edit.ref = lhb + rhb
                        hgvs_genomic.posedit.edit.alt = lhb + hgvs_genomic.posedit.edit.alt + rhb
                        hgvs_genomic.posedit.pos.start.base = end
                        hgvs_genomic.posedit.pos.end.base = start
                        reverse_normalized_hgvs_genomic = self.variant.reverse_normalizer.normalize(
                            hgvs_genomic)
                    if hgvs_genomic.posedit.edit.type == 'del':
                        start = hgvs_genomic.posedit.pos.start.base
                        end = hgvs_genomic.posedit.pos.end.base
                        lhb = self.validator.sf.fetch_seq(str(hgvs_genomic.ac), end - 1, end)
                        rhb = self.validator.sf.fetch_seq(str(hgvs_genomic.ac), start - 1, start)
                        hgvs_genomic.posedit.edit.ref = lhb + rhb
                        hgvs_genomic.posedit.edit.alt = lhb + rhb
                        hgvs_genomic.posedit.pos.start.base = end
                        hgvs_genomic.posedit.pos.end.base = start
                        reverse_normalized_hgvs_genomic = self.variant.reverse_normalizer.normalize(
                            hgvs_genomic)
                if 'insertion length must be 1' in error:
                    if hgvs_genomic.posedit.edit.type == 'ins':
                        start = hgvs_genomic.posedit.pos.start.base
                        end = hgvs_genomic.posedit.pos.end.base
                        ref_bases = self.validator.sf.fetch_seq(str(hgvs_genomic.ac), start - 1, end)
                        lhb = self.validator.sf.fetch_seq(str(hgvs_genomic.ac), start - 1, start)
                        rhb = self.validator.sf.fetch_seq(str(hgvs_genomic.ac), start, end)
                        hgvs_genomic.posedit.edit.ref = lhb + rhb
                        hgvs_genomic.posedit.edit.alt = lhb + hgvs_genomic.posedit.edit.alt + rhb
                        reverse_normalized_hgvs_genomic = self.variant.reverse_normalizer.normalize(
                            hgvs_genomic)

            self.hgvs_genomic_5pr = copy.deepcopy(reverse_normalized_hgvs_genomic)
            # Store a copy for later use

            # Make VCF
            vcf_dict = vvHGVS.hgvs2vcf(reverse_normalized_hgvs_genomic, self.variant.primary_assembly,
                                       self.variant.reverse_normalizer, self.validator.sf)
            chr = vcf_dict['chr']
            pos = vcf_dict['pos']
            ref = vcf_dict['ref']
            alt = vcf_dict['alt']

            # Look for exonic gaps within transcript or chromosome

            # Generate an end position
            end = str(int(pos) + len(ref) - 1)
            pos = str(pos)

            # Store a not real deletion insertion to test for gapping
            stored_hgvs_not_delins = self.validator.hp.parse_hgvs_variant(str(
                self.hgvs_genomic_5pr.ac) + ':' + self.hgvs_genomic_5pr.type + '.' + pos + '_' + end + 'del' +
                                                                          ref + 'ins' + alt)
            # Save a copy of current hgvs_coding
            saved_hgvs_coding = ''
            try:
                saved_hgvs_coding = self.variant.no_norm_evm.g_to_t(stored_hgvs_not_delins,
                                                               hgvs_coding.ac)
            except Exception as e:
                if str(e) == 'start or end or both are beyond the bounds of transcript record':
                    saved_hgvs_coding = hgvs_coding
                    continue

            # Detect intronic variation using normalization
            intronic_variant = 'false'
            # Look for normalized variant options that do not match hgvs_coding
            hgvs_seek_var = self.get_hgvs_seek_var(hgvs_genomic, hgvs_coding)
            if (
                    hgvs_seek_var.posedit.pos.start.base + hgvs_seek_var.posedit.pos.start.offset) > (
                    hgvs_coding.posedit.pos.start.base + hgvs_coding.posedit.pos.start.offset) and (
                    hgvs_seek_var.posedit.pos.end.base + hgvs_seek_var.posedit.pos.end.offset) > (
                    hgvs_coding.posedit.pos.end.base + hgvs_coding.posedit.pos.end.offset) and rec_var != 'false':
                pass
            else:
                hgvs_seek_var = saved_hgvs_coding

            try:
                self.variant.hn.normalize(hgvs_seek_var)
            except hgvs.exceptions.HGVSUnsupportedOperationError as e:
                error = str(e)
                if 'Normalization of intronic variants is not supported' in error or \
                        'Unsupported normalization of variants spanning the exon-intron boundary' in error:
                    if 'Unsupported normalization of variants spanning the exon-intron boundary' in error:
                        intronic_variant = 'hard_fail'
                    else:
                        # Double check to see whether the variant is actually intronic?
                        for exon in ori:
                            genomic_start = int(exon['alt_start_i'])
                            genomic_end = int(exon['alt_end_i'])
                            if (genomic_start < self.hgvs_genomic_5pr.posedit.pos.start.base <= genomic_end) and (
                                    genomic_start < self.hgvs_genomic_5pr.posedit.pos.end.base <= genomic_end):
                                intronic_variant = 'false'
                                break
                            else:
                                intronic_variant = 'true'

            if intronic_variant != 'hard_fail':
                if re.search(r'\d+\+', str(hgvs_seek_var.posedit.pos)) or re.search(r'\d+-',
                    str(hgvs_seek_var.posedit.pos)) or re.search(r'\*\d+\+', str(
                        hgvs_seek_var.posedit.pos)) or re.search(r'\*\d+-', str(hgvs_seek_var.posedit.pos)):
                    # Double check to see whether the variant is actually intronic?
                    for exon in ori:
                        genomic_start = int(exon['alt_start_i'])
                        genomic_end = int(exon['alt_end_i'])
                        if (genomic_start < self.hgvs_genomic_5pr.posedit.pos.start.base <= genomic_end) and (
                                genomic_start < self.hgvs_genomic_5pr.posedit.pos.end.base <= genomic_end):
                            intronic_variant = 'false'
                            break
                        else:
                            intronic_variant = 'true'

            if intronic_variant != 'true':
                # Flag RefSeqGene for ammendment
                # amend_RefSeqGene = 'false'
                # Attempt to find gaps in reference sequence by catching disparity in genome length and overlapping
                # transcript lengths
                hgvs_not_delins = ''
                if stored_hgvs_not_delins != '':
                    # Refresh hgvs_not_delins from stored_hgvs_not_delins
                    hgvs_not_delins = self.dup_ins_5prime_shift(stored_hgvs_not_delins, saved_hgvs_coding)

                    self.tx_hgvs_not_delins = self.variant.no_norm_evm.g_to_n(hgvs_not_delins, saved_hgvs_coding.ac)
                    # Create normalized version of tx_hgvs_not_delins
                    rn_tx_hgvs_not_delins = copy.deepcopy(self.tx_hgvs_not_delins)
                    # Check for +1 base and adjust
                    if '+' in str(rn_tx_hgvs_not_delins.posedit.pos.end) and '+' in str(
                            rn_tx_hgvs_not_delins.posedit.pos.start):
                        rn_tx_hgvs_not_delins = self.remove_offsetting_to_span_gap(rn_tx_hgvs_not_delins)

                    elif '+' in str(rn_tx_hgvs_not_delins.posedit.pos.end):
                        rn_tx_hgvs_not_delins, hgvs_not_delins = self.move_tx_end_base_to_next_nonoffset(
                            rn_tx_hgvs_not_delins, saved_hgvs_coding, back=False)

                    elif '+' in str(rn_tx_hgvs_not_delins.posedit.pos.start):
                        rn_tx_hgvs_not_delins, hgvs_not_delins = self.move_tx_start_base_to_previous_nonoffset(
                            rn_tx_hgvs_not_delins, saved_hgvs_coding)

                    # Check for -ve base and adjust
                    elif '-' in str(rn_tx_hgvs_not_delins.posedit.pos.end) and '-' in str(
                            rn_tx_hgvs_not_delins.posedit.pos.start):
                        rn_tx_hgvs_not_delins = self.remove_offsetting_to_span_gap(rn_tx_hgvs_not_delins)

                    elif '-' in str(rn_tx_hgvs_not_delins.posedit.pos.end):
                        rn_tx_hgvs_not_delins, hgvs_not_delins = self.move_tx_end_base_to_next_nonoffset(
                            rn_tx_hgvs_not_delins, saved_hgvs_coding)

                    elif '-' in str(rn_tx_hgvs_not_delins.posedit.pos.start):
                        rn_tx_hgvs_not_delins, hgvs_not_delins = self.move_tx_start_base_to_previous_nonoffset(
                            rn_tx_hgvs_not_delins, saved_hgvs_coding, with_base_subtract=True)

                    # Logic

                    hgvs_not_delins = self.logic_check(hgvs_not_delins, rn_tx_hgvs_not_delins, hgvs_coding,
                                                       do_continue=True, offset_check=True)

                # Final sanity checks
                try:
                    self.validator.vm.g_to_t(hgvs_not_delins, self.tx_hgvs_not_delins.ac)
                except Exception as e:
                    if str(e) == 'start or end or both are beyond the bounds of transcript record':
                        continue
                try:
                    self.variant.hn.normalize(self.tx_hgvs_not_delins)
                except hgvs.exceptions.HGVSUnsupportedOperationError as e:
                    error = str(e)
                    if 'Normalization of intronic variants is not supported' in error or \
                            'Unsupported normalization of variants spanning the exon-intron boundary' in error:
                        if 'Unsupported normalization of variants spanning the exon-intron boundary' in error:
                            continue
                        elif 'Normalization of intronic variants is not supported' in error:
                            # We know that this cannot be because of an intronic variant, so must be aligned to tx gap
                            self.disparity_deletion_in = ['transcript', 'Requires Analysis']

                # Recreate hgvs_genomic
                if self.disparity_deletion_in[0] == 'transcript':
                    hgvs_genomic = hgvs_not_delins

                # Find oddly placed gaps where the tx variant is encompassed in the gap
                if self.disparity_deletion_in[0] == 'false' and (
                        possibility_counter == 3 or possibility_counter == 4):
                    rg = self.variant.reverse_normalizer.normalize(hgvs_not_delins)
                    rtx = self.validator.vm.g_to_t(rg, self.tx_hgvs_not_delins.ac)
                    fg = self.variant.hn.normalize(hgvs_not_delins)
                    ftx = self.validator.vm.g_to_t(fg, self.tx_hgvs_not_delins.ac)
                    if (rtx.posedit.pos.start.offset == 0 and rtx.posedit.pos.end.offset == 0) and (
                            ftx.posedit.pos.start.offset != 0 and ftx.posedit.pos.end.offset != 0):
                        exons = self.validator.hdp.get_tx_exons(ftx.ac, hgvs_not_delins.ac,
                                                                self.validator.alt_aln_method)
                        exonic = False
                        for ex_test in exons:
                            if ftx.posedit.pos.start.base in range(ex_test[6], ex_test[7]) and \
                                    ftx.posedit.pos.end.base in range(ex_test[6], ex_test[7]):
                                exonic = True
                        if exonic is True:
                            hgvs_genomic = fg
                            self.hgvs_genomic_5pr = fg
                            try:
                                self.tx_hgvs_not_delins = self.validator.vm.c_to_n(ftx)
                            except Exception:
                                self.tx_hgvs_not_delins = ftx
                            self.disparity_deletion_in = ['transcript', 'Requires Analysis']

                # Pre-processing of tx_hgvs_not_delins
                try:
                    if self.tx_hgvs_not_delins.posedit.edit.alt is None:
                        self.tx_hgvs_not_delins.posedit.edit.alt = ''
                except Exception as e:
                    if str(e) == "'Dup' object has no attribute 'alt'":
                        tx_hgvs_not_delins_delins_from_dup = fn.hgvs_dup2indel(self.tx_hgvs_not_delins)
                        self.tx_hgvs_not_delins = self.validator.hp.parse_hgvs_variant(
                            tx_hgvs_not_delins_delins_from_dup)

                if self.disparity_deletion_in[0] == 'transcript':
                    # amend_RefSeqGene = 'true'
                    # ANY VARIANT WHOLLY WITHIN THE GAP
                    hgvs_refreshed_variant = self.transcript_disparity(reverse_normalized_hgvs_genomic,
                                                                       stored_hgvs_not_delins, hgvs_genomic, 4)

                # GAP IN THE CHROMOSOME
                elif self.disparity_deletion_in[0] == 'chromosome':
                    # amend_RefSeqGene = 'true'
                    if possibility_counter == 3:
                        hgvs_refreshed_variant = stash_tx_right
                    elif possibility_counter == 4:
                        hgvs_refreshed_variant = stash_tx_left
                    else:
                        hgvs_refreshed_variant = chromosome_normalized_hgvs_coding
                    # Warn
                    self.auto_info = self.auto_info + str(hgvs_refreshed_variant.ac) + ':c.' + str(
                        hgvs_refreshed_variant.posedit.pos) + ' contains ' + str(
                        self.disparity_deletion_in[
                            1]) + ' transcript base(s) that fail to align to chromosome ' + str(
                        hgvs_genomic.ac) + '\n'
                else:
                    # Keep the same by re-setting rel_var
                    hgvs_refreshed_variant = hgvs_coding

                # Edit the output
                if 'NM_' in str(hgvs_refreshed_variant.ac) and 'c' not in str(hgvs_refreshed_variant.type):
                    hgvs_refreshed_variant = self.variant.no_norm_evm.n_to_c(hgvs_refreshed_variant)

                try:
                    self.variant.hn.normalize(hgvs_refreshed_variant)
                except Exception as e:
                    error = str(e)
                    # Ensure the final variant is not intronic nor does it cross exon boundaries
                    if 'Normalization of intronic variants is not supported' in error or \
                            'Unsupported normalization of variants spanning the exon-intron boundary' in error:
                        hgvs_refreshed_variant = saved_hgvs_coding
                    else:
                        continue

                # Quick check to make sure the coding variant has not changed
                try:
                    to_test = self.variant.hn.normalize(hgvs_refreshed_variant)
                except:
                    to_test = hgvs_refreshed_variant
                if str(to_test.posedit.edit) != str(hgvs_coding.posedit.edit):
                    # Try the next available genomic option
                    if hgvs_coding.posedit.edit.type == 'identity' and to_test.posedit.edit.type == 'identity':
                        hgvs_coding = to_test
                    else:
                        continue

                # Update hgvs_genomic
                hgvs_alt_genomic = self.validator.myvm_t_to_g(hgvs_refreshed_variant, alt_chr,
                                                              self.variant.no_norm_evm, self.variant.hn)
                if hgvs_alt_genomic.posedit.edit.type == 'identity':
                    re_c = self.validator.vm.g_to_t(hgvs_alt_genomic, hgvs_refreshed_variant.ac)
                    if (self.variant.hn.normalize(re_c)) != (self.variant.hn.normalize(hgvs_refreshed_variant)):
                        shuffle_left_g = copy.copy(hgvs_alt_genomic)
                        shuffle_left_g.posedit.edit.ref = ''
                        shuffle_left_g.posedit.edit.alt = ''
                        shuffle_left_g.posedit.pos.start.base = shuffle_left_g.posedit.pos.start.base - 1
                        shuffle_left_g.posedit.pos.end.base = shuffle_left_g.posedit.pos.end.base - 1
                        shuffle_left_g = self.variant.reverse_normalizer.normalize(shuffle_left_g)
                        re_c = self.validator.vm.g_to_t(shuffle_left_g, hgvs_refreshed_variant.ac)
                        if (self.variant.hn.normalize(re_c)) != (self.variant.hn.normalize(hgvs_refreshed_variant)):
                            hgvs_alt_genomic = shuffle_left_g

                            # If it is intronic, these vairables will not have been set

            # Break if gap has been detected
            if self.disparity_deletion_in[0] != 'false':
                break

        # Normailse hgvs_genomic
        try:
            hgvs_alt_genomic = self.variant.hn.normalize(hgvs_alt_genomic)
        except hgvs.exceptions.HGVSError as e:
            # Strange error caused by gap in genomic
            error = str(e)
            if 'base start position must be <= end position' in error and self.disparity_deletion_in[0] == 'chromosome':
                if hgvs_alt_genomic.posedit.edit.type == 'delins':
                    start = hgvs_alt_genomic.posedit.pos.start.base
                    end = hgvs_alt_genomic.posedit.pos.end.base
                    lhb = self.validator.sf.fetch_seq(str(hgvs_alt_genomic.ac), end - 1, end)
                    rhb = self.validator.sf.fetch_seq(str(hgvs_alt_genomic.ac), start - 1, start)
                    hgvs_alt_genomic.posedit.edit.ref = lhb + rhb
                    hgvs_alt_genomic.posedit.edit.alt = lhb + hgvs_alt_genomic.posedit.edit.alt + rhb
                    hgvs_alt_genomic.posedit.pos.start.base = end
                    hgvs_alt_genomic.posedit.pos.end.base = start
                    hgvs_alt_genomic = self.variant.hn.normalize(hgvs_alt_genomic)
                if hgvs_alt_genomic.posedit.edit.type == 'del':
                    start = hgvs_alt_genomic.posedit.pos.start.base
                    end = hgvs_alt_genomic.posedit.pos.end.base
                    lhb = self.validator.sf.fetch_seq(str(hgvs_alt_genomic.ac), end - 1, end)
                    rhb = self.validator.sf.fetch_seq(str(hgvs_alt_genomic.ac), start - 1, start)
                    hgvs_alt_genomic.posedit.edit.ref = lhb + rhb
                    hgvs_alt_genomic.posedit.edit.alt = lhb + rhb
                    hgvs_alt_genomic.posedit.pos.start.base = end
                    hgvs_alt_genomic.posedit.pos.end.base = start
                    hgvs_alt_genomic = self.variant.hn.normalize(hgvs_alt_genomic)

        return hgvs_alt_genomic, hgvs_coding

    def dup_ins_5prime_shift(self, stored_hgvs_not_delins, saved_hgvs_coding):
        hgvs_not_delins = copy.deepcopy(stored_hgvs_not_delins)
        # This test will only occur in dup of single base, insertion or substitution
        if '_' not in str(hgvs_not_delins.posedit.pos):
            if 'dup' in self.hgvs_genomic_5pr.posedit.edit.type or 'ins' in self.hgvs_genomic_5pr.posedit.edit.type:
                # For gap in chr, map to t. - but because we have pushed to 5 prime by norm, add 1 to end pos
                plussed_hgvs_not_delins = copy.deepcopy(hgvs_not_delins)
                plussed_hgvs_not_delins.posedit.pos.end.base = plussed_hgvs_not_delins.posedit.pos.end.base + 1
                plussed_hgvs_not_delins.posedit.edit.ref = ''
                transcript_variant = self.variant.no_norm_evm.g_to_t(plussed_hgvs_not_delins,
                                                                     str(saved_hgvs_coding.ac))
                if ((transcript_variant.posedit.pos.end.base - transcript_variant.posedit.pos.start.base) > (
                        self.hgvs_genomic_5pr.posedit.pos.end.base - self.hgvs_genomic_5pr.posedit.pos.start.base)):
                    if 'dup' in str(self.hgvs_genomic_5pr.posedit.edit):
                        hgvs_not_delins.posedit.pos.end.base = hgvs_not_delins.posedit.pos.start.base + 1
                        start = hgvs_not_delins.posedit.pos.start.base - 1
                        end = hgvs_not_delins.posedit.pos.end.base
                        ref_bases = self.validator.sf.fetch_seq(str(hgvs_not_delins.ac), start, end)
                        hgvs_not_delins.posedit.edit.ref = ref_bases
                        hgvs_not_delins.posedit.edit.alt = ref_bases[:1] + hgvs_not_delins.posedit.edit.alt[
                                                                 1:] + ref_bases[1:]
                    elif 'ins' in str(self.hgvs_genomic_5pr.posedit.edit) and \
                            'del' in str(self.hgvs_genomic_5pr.posedit.edit):
                        hgvs_not_delins.posedit.pos.end.base = hgvs_not_delins.posedit.pos.start.base + 1
                    elif 'ins' in str(self.hgvs_genomic_5pr.posedit.edit) and \
                            'del' not in str(self.hgvs_genomic_5pr.posedit.edit):
                        hgvs_not_delins.posedit.pos.end.base = hgvs_not_delins.posedit.pos.start.base + 1
                        start = hgvs_not_delins.posedit.pos.start.base - 1
                        end = hgvs_not_delins.posedit.pos.end.base
                        ref_bases = self.validator.sf.fetch_seq(str(hgvs_not_delins.ac), start, end)
                        hgvs_not_delins.posedit.edit.ref = ref_bases
                        hgvs_not_delins.posedit.edit.alt = ref_bases[:1] + hgvs_not_delins.posedit.edit.alt[
                                                                 1:] + ref_bases[1:]
                else:
                    if 'dup' in str(self.hgvs_genomic_5pr.posedit.edit):
                        hgvs_not_delins.posedit.pos.end.base = hgvs_not_delins.posedit.pos.start.base + 1
                        start = hgvs_not_delins.posedit.pos.start.base - 1
                        end = hgvs_not_delins.posedit.pos.end.base
                        ref_bases = self.validator.sf.fetch_seq(str(hgvs_not_delins.ac), start, end)
                        hgvs_not_delins.posedit.edit.ref = ref_bases
                        hgvs_not_delins.posedit.edit.alt = ref_bases[:1] + hgvs_not_delins.posedit.edit.alt[
                                                                 1:] + ref_bases[1:]
                    elif 'ins' in str(self.hgvs_genomic_5pr.posedit.edit) and \
                            'del' in str(self.hgvs_genomic_5pr.posedit.edit):
                        hgvs_not_delins.posedit.pos.end.base = hgvs_not_delins.posedit.pos.start.base + 1
                    elif 'ins' in str(self.hgvs_genomic_5pr.posedit.edit) and \
                            'del' not in str(self.hgvs_genomic_5pr.posedit.edit):
                        hgvs_not_delins.posedit.pos.end.base = hgvs_not_delins.posedit.pos.start.base + 1
                        start = hgvs_not_delins.posedit.pos.start.base - 1
                        end = hgvs_not_delins.posedit.pos.end.base
                        ref_bases = self.validator.sf.fetch_seq(str(hgvs_not_delins.ac), start, end)
                        hgvs_not_delins.posedit.edit.ref = ref_bases
                        hgvs_not_delins.posedit.edit.alt = ref_bases[:1] + hgvs_not_delins.posedit.edit.alt[
                                                                 1:] + ref_bases[1:]

        return hgvs_not_delins

    def remove_offsetting_to_span_gap(self, rn_tx_hgvs_not_delins):
        # Remove offsetting to span the gap
        rn_tx_hgvs_not_delins.posedit.pos.start.offset = 0
        rn_tx_hgvs_not_delins.posedit.pos.end.offset = 0
        rn_tx_hgvs_not_delins.posedit.pos.end.base = rn_tx_hgvs_not_delins.posedit.pos.end.base + 1
        rn_tx_hgvs_not_delins.posedit.edit.ref = ''
        try:
            rn_tx_hgvs_not_delins.posedit.edit.alt = ''
        except:
            pass

        return rn_tx_hgvs_not_delins

    def move_tx_end_base_to_next_nonoffset(self, rn_tx_hgvs_not_delins, saved_hgvs_coding, back=True):
        # move tx end base back to next available non-offset base
        rn_tx_hgvs_not_delins.posedit.pos.end.offset = 0
        rn_tx_hgvs_not_delins.posedit.edit.ref = ''
        if back:
            # Add the additional base to the ALT
            start = rn_tx_hgvs_not_delins.posedit.pos.end.base - 1
            end = rn_tx_hgvs_not_delins.posedit.pos.end.base
            ref_bases = self.validator.sf.fetch_seq(str(self.tx_hgvs_not_delins.ac), start, end)
            rn_tx_hgvs_not_delins.posedit.edit.alt = rn_tx_hgvs_not_delins.posedit.edit.alt + ref_bases
        else:
            # move tx end base to next available non-offset base
            rn_tx_hgvs_not_delins.posedit.pos.end.base = self.tx_hgvs_not_delins.posedit.pos.end.base + 1
        if 'NM_' in str(rn_tx_hgvs_not_delins):
            test_tx_var = self.variant.no_norm_evm.n_to_c(rn_tx_hgvs_not_delins)
        else:
            test_tx_var = rn_tx_hgvs_not_delins
        # re-make genomic and tx
        hgvs_not_delins = self.validator.myevm_t_to_g(test_tx_var, self.variant.no_norm_evm,
                                                      self.variant.primary_assembly, self.variant.hn)
        rn_tx_hgvs_not_delins = self.variant.no_norm_evm.g_to_n(hgvs_not_delins,
                                                                str(saved_hgvs_coding.ac))
        return rn_tx_hgvs_not_delins, hgvs_not_delins

    def move_tx_start_base_to_previous_nonoffset(self, rn_tx_hgvs_not_delins, saved_hgvs_coding,
                                                 with_base_subtract=False):
        # move tx start base to previous available non-offset base
        rn_tx_hgvs_not_delins.posedit.pos.start.offset = 0
        if with_base_subtract:
            rn_tx_hgvs_not_delins.posedit.pos.start.base = rn_tx_hgvs_not_delins.posedit.pos.start.base - 1
        rn_tx_hgvs_not_delins.posedit.edit.ref = ''
        if 'NM_' in str(rn_tx_hgvs_not_delins):
            test_tx_var = self.variant.no_norm_evm.n_to_c(rn_tx_hgvs_not_delins)
        else:
            test_tx_var = rn_tx_hgvs_not_delins
        # re-make genomic and tx
        hgvs_not_delins = self.validator.myevm_t_to_g(test_tx_var, self.variant.no_norm_evm,
                                                      self.variant.primary_assembly, self.variant.hn)
        rn_tx_hgvs_not_delins = self.variant.no_norm_evm.g_to_n(hgvs_not_delins,
                                                                str(saved_hgvs_coding.ac))
        rn_tx_hgvs_not_delins.posedit.pos.start.offset = 0

        return rn_tx_hgvs_not_delins, hgvs_not_delins

    def c2_pos_edit(self, hgvs_genomic):
        try:
            c2 = self.validator.vm.n_to_c(self.tx_hgvs_not_delins)
        except:
            c2 = self.tx_hgvs_not_delins
        c1 = copy.deepcopy(c2)
        c1.posedit.pos.start.base = c2.posedit.pos.start.base - 1
        c1.posedit.pos.start.offset = 0
        c1.posedit.pos.end = c2.posedit.pos.start
        c1.posedit.edit.ref = ''
        c1.posedit.edit.alt = ''
        if self.orientation != -1:
            g1 = self.validator.vm.t_to_g(c1, hgvs_genomic.ac)
            g2 = self.validator.vm.t_to_g(c2, hgvs_genomic.ac)
            g1.posedit.edit.alt = g1.posedit.edit.ref
        else:
            g1 = self.validator.vm.t_to_g(c2, hgvs_genomic.ac)
            g2 = self.validator.vm.t_to_g(c1, hgvs_genomic.ac)
            g2.posedit.edit.alt = g2.posedit.edit.ref
        reference = g1.posedit.edit.ref + g2.posedit.edit.ref[1:]
        alternate = g1.posedit.edit.alt + g2.posedit.edit.alt[1:]
        g3 = copy.deepcopy(g1)
        g3.posedit.pos.end.base = g2.posedit.pos.end.base
        g3.posedit.edit.ref = reference
        g3.posedit.edit.alt = alternate
        c3 = self.validator.vm.g_to_t(g3, c1.ac)
        hgvs_refreshed_variant = c3

        return hgvs_refreshed_variant

    def c1_pos_edit(self, hgvs_genomic):
        try:
            c1 = self.validator.vm.n_to_c(self.tx_hgvs_not_delins)
        except:
            c1 = self.tx_hgvs_not_delins
        c2 = copy.deepcopy(c1)
        c2.posedit.pos.start = c1.posedit.pos.end
        c2.posedit.pos.end.base = c1.posedit.pos.end.base + 1
        c2.posedit.pos.end.offset = 0
        c2.posedit.edit.ref = ''
        c2.posedit.edit.alt = ''
        if self.orientation != -1:
            g1 = self.validator.vm.t_to_g(c1, hgvs_genomic.ac)
            g2 = self.validator.vm.t_to_g(c2, hgvs_genomic.ac)
            g2.posedit.edit.alt = g2.posedit.edit.ref
        else:
            g1 = self.validator.vm.t_to_g(c2, hgvs_genomic.ac)
            g2 = self.validator.vm.t_to_g(c1, hgvs_genomic.ac)
            g1.posedit.edit.alt = g1.posedit.edit.ref
        reference = g1.posedit.edit.ref + g2.posedit.edit.ref[1:]
        alternate = g1.posedit.edit.alt + g2.posedit.edit.alt[1:]
        g3 = copy.deepcopy(g1)
        g3.posedit.pos.end.base = g2.posedit.pos.end.base
        g3.posedit.edit.ref = reference
        g3.posedit.edit.alt = alternate
        c3 = self.validator.vm.g_to_t(g3, c1.ac)
        hgvs_refreshed_variant = c3

        return hgvs_refreshed_variant

    def transcript_disparity(self, reverse_normalized_hgvs_genomic, stored_hgvs_not_delins, hgvs_genomic,
                             running_option):
        if ('+' in str(self.tx_hgvs_not_delins.posedit.pos.start) or '-' in str(
                self.tx_hgvs_not_delins.posedit.pos.start)) and (
                '+' in str(self.tx_hgvs_not_delins.posedit.pos.end) or '-' in str(
                self.tx_hgvs_not_delins.posedit.pos.end)):
            self.gapped_transcripts = self.gapped_transcripts + ' ' + str(self.tx_hgvs_not_delins.ac)

            # Copy the current variant
            tx_gap_fill_variant = copy.deepcopy(self.tx_hgvs_not_delins)
            try:
                if tx_gap_fill_variant.posedit.edit.alt is None:
                    tx_gap_fill_variant.posedit.edit.alt = ''
            except Exception as e:
                if str(e) == "'Dup' object has no attribute 'alt'":
                    tx_gap_fill_variant_delins_from_dup = fn.hgvs_dup2indel(tx_gap_fill_variant)
                    tx_gap_fill_variant = self.validator.hp.parse_hgvs_variant(
                        tx_gap_fill_variant_delins_from_dup)

            # Identify which half of the NOT-intron the start position of the variant is in
            if '-' in str(tx_gap_fill_variant.posedit.pos.start):
                tx_gap_fill_variant.posedit.pos.start.base = tx_gap_fill_variant.posedit.pos.start.base - 1
                tx_gap_fill_variant.posedit.pos.start.offset = int('0')  # int('+1')
                tx_gap_fill_variant.posedit.pos.end.offset = int('0')  # int('-1')
                tx_gap_fill_variant.posedit.edit.alt = ''
                tx_gap_fill_variant.posedit.edit.ref = ''
            elif '+' in str(tx_gap_fill_variant.posedit.pos.start):
                tx_gap_fill_variant.posedit.pos.start.offset = int('0')  # int('+1')
                tx_gap_fill_variant.posedit.pos.end.base = tx_gap_fill_variant.posedit.pos.end.base + 1
                tx_gap_fill_variant.posedit.pos.end.offset = int('0')  # int('-1')
                tx_gap_fill_variant.posedit.edit.alt = ''
                tx_gap_fill_variant.posedit.edit.ref = ''

            try:
                tx_gap_fill_variant = self.validator.vm.n_to_c(tx_gap_fill_variant)
            except:
                fn.exceptPass()
            genomic_gap_fill_variant = self.validator.vm.t_to_g(tx_gap_fill_variant, reverse_normalized_hgvs_genomic.ac)
            genomic_gap_fill_variant.posedit.edit.alt = genomic_gap_fill_variant.posedit.edit.ref

            try:
                c_tx_hgvs_not_delins = self.validator.vm.n_to_c(self.tx_hgvs_not_delins)
            except Exception:
                c_tx_hgvs_not_delins = copy.copy(self.tx_hgvs_not_delins)
            genomic_gap_fill_variant_alt = self.validator.vm.t_to_g(c_tx_hgvs_not_delins, self.hgvs_genomic_5pr.ac)

            # Ensure an ALT exists
            try:
                if genomic_gap_fill_variant_alt.posedit.edit.alt is None:
                    genomic_gap_fill_variant_alt.posedit.edit.alt = 'X'
            except Exception as e:
                if str(e) == "'Dup' object has no attribute 'alt'":
                    genomic_gap_fill_variant_delins_from_dup = fn.hgvs_dup2indel(genomic_gap_fill_variant)
                    genomic_gap_fill_variant = self.validator.hp.parse_hgvs_variant(
                        genomic_gap_fill_variant_delins_from_dup)
                    genomic_gap_fill_variant_alt_delins_from_dup = fn.hgvs_dup2indel(genomic_gap_fill_variant_alt)
                    genomic_gap_fill_variant_alt = self.validator.hp.parse_hgvs_variant(
                        genomic_gap_fill_variant_alt_delins_from_dup)

            # Correct insertion alts
            if genomic_gap_fill_variant_alt.posedit.edit.type == 'ins':
                append_ref = self.validator.sf.fetch_seq(genomic_gap_fill_variant_alt.ac,
                                                         genomic_gap_fill_variant_alt.posedit.pos.start.base - 1,
                                                         genomic_gap_fill_variant_alt.posedit.pos.end.base)
                genomic_gap_fill_variant_alt.posedit.edit.alt = append_ref[0] + \
                    genomic_gap_fill_variant_alt.posedit.edit.alt + append_ref[1]

            # Split the reference and replacing alt sequence into a dictionary
            reference_bases = list(genomic_gap_fill_variant.posedit.edit.ref)
            if genomic_gap_fill_variant_alt.posedit.edit.alt is not None:
                alternate_bases = list(genomic_gap_fill_variant_alt.posedit.edit.alt)
            else:
                # Deletions with no ins
                pre_alternate_bases = list(genomic_gap_fill_variant_alt.posedit.edit.ref)
                alternate_bases = []
                for base in pre_alternate_bases:
                    alternate_bases.append('X')

            # Create the dictionaries
            ref_start = genomic_gap_fill_variant.posedit.pos.start.base
            alt_start = genomic_gap_fill_variant_alt.posedit.pos.start.base
            ref_base_dict = {}
            for base in reference_bases:
                ref_base_dict[ref_start] = str(base)
                ref_start = ref_start + 1

            alt_base_dict = {}

            # NEED TO SEARCH FOR RANGE = and replace with interval_range
            # Need to search for int and replace with integer

            # Note, all variants will be forced into the format delete insert
            # Deleted bases in the ALT will be substituted for X
            for integer in range(genomic_gap_fill_variant_alt.posedit.pos.start.base,
                                 genomic_gap_fill_variant_alt.posedit.pos.end.base + 1, 1):
                if integer == alt_start:
                    alt_base_dict[integer] = str(''.join(alternate_bases))
                else:
                    alt_base_dict[integer] = 'X'

            # Generate the alt sequence
            alternate_sequence_bases = []
            for integer in range(genomic_gap_fill_variant.posedit.pos.start.base,
                                 genomic_gap_fill_variant.posedit.pos.end.base + 1, 1):
                if integer in list(alt_base_dict.keys()):
                    alternate_sequence_bases.append(alt_base_dict[integer])
                else:
                    alternate_sequence_bases.append(ref_base_dict[integer])
            alternate_sequence = ''.join(alternate_sequence_bases)
            alternate_sequence = alternate_sequence.replace('X', '')

            # Add the new alt to the gap fill variant and generate transcript variant
            genomic_gap_fill_variant.posedit.edit.alt = alternate_sequence
            hgvs_refreshed_variant = self.validator.vm.g_to_t(genomic_gap_fill_variant, tx_gap_fill_variant.ac)

            # Set warning
            gap_size = str(len(genomic_gap_fill_variant.posedit.edit.ref) - 2)
            self.disparity_deletion_in[1] = [gap_size]
            self.auto_info = self.auto_info + str(stored_hgvs_not_delins.ac) + ':g.' + str(
                stored_hgvs_not_delins.posedit.pos.start.base) + ' is one of ' + gap_size + \
                ' genomic base(s) that fail to align to transcript ' + str(self.tx_hgvs_not_delins.ac)

            # Alignment position
            for_location_c = copy.deepcopy(hgvs_refreshed_variant)
            if 'NM_' in str(for_location_c):
                for_location_c = self.variant.no_norm_evm.n_to_c(self.tx_hgvs_not_delins)
            if '-' in str(for_location_c.posedit.pos.start.offset):
                gps = for_location_c.posedit.pos.start.base - 1
                gpe = for_location_c.posedit.pos.start.base
            else:
                gps = for_location_c.posedit.pos.start.base
                gpe = for_location_c.posedit.pos.start.base + 1
            gap_position = ' between positions c.' + str(gps) + '_' + str(gpe) + '\n'
            self.auto_info = self.auto_info + '%s' % (gap_position)

        else:
            if self.tx_hgvs_not_delins.posedit.pos.start.offset == 0 and \
                    self.tx_hgvs_not_delins.posedit.pos.end.offset == 0:
                # In this instance, we have identified a transcript gap but the n. version of
                # the transcript variant but do not have a position which actually hits the gap,
                # so the variant likely spans the gap, and is not picked up by an offset.
                try:
                    c1 = self.validator.vm.n_to_c(self.tx_hgvs_not_delins)
                except:
                    c1 = self.tx_hgvs_not_delins
                g1 = self.validator.nr_vm.t_to_g(c1, hgvs_genomic.ac)
                g3 = self.validator.nr_vm.t_to_g(c1, hgvs_genomic.ac)
                g2 = self.validator.vm.t_to_g(c1, hgvs_genomic.ac)
                ng2 = self.variant.hn.normalize(g2)
                g3.posedit.pos.end.base = g3.posedit.pos.start.base + (len(g3.posedit.edit.ref) - 1)
                try:
                    c2 = self.validator.vm.g_to_t(g3, c1.ac)
                    if c2.posedit.pos.start.offset == 0 and c2.posedit.pos.end.offset == 0:
                        pass
                    else:
                        self.tx_hgvs_not_delins = c2
                        try:
                            self.tx_hgvs_not_delins = self.validator.vm.c_to_n(self.tx_hgvs_not_delins)
                        except hgvs.exceptions.HGVSError:
                            fn.exceptPass()
                except hgvs.exceptions.HGVSInvalidVariantError:
                    fn.exceptPass()

            if '+' in str(self.tx_hgvs_not_delins.posedit.pos.start) and \
                    '+' not in str(self.tx_hgvs_not_delins.posedit.pos.end):
                self.auto_info = self.auto_info + str(stored_hgvs_not_delins.ac) + ':g.' + str(
                    stored_hgvs_not_delins.posedit.pos.start.base) + ' is one of ' + str(
                    self.disparity_deletion_in[
                        1]) + ' genomic base(s) that fail to align to transcript ' + str(
                    self.tx_hgvs_not_delins.ac)
                hgvs_refreshed_variant = self.c2_pos_edit(hgvs_genomic)

                # Alignment position
                for_location_c = copy.deepcopy(hgvs_refreshed_variant)
                if 'NM_' in str(for_location_c):
                    for_location_c = self.variant.no_norm_evm.n_to_c(self.tx_hgvs_not_delins)
                gps = for_location_c.posedit.pos.start.base
                gpe = for_location_c.posedit.pos.start.base + 1
                gap_position = ' between positions c.' + str(gps) + '_' + str(gpe) + '\n'
                # Warn update
                self.auto_info = self.auto_info + '%s' % gap_position
            elif '+' in str(self.tx_hgvs_not_delins.posedit.pos.end) and \
                    '+' not in str(self.tx_hgvs_not_delins.posedit.pos.start):
                self.auto_info = self.auto_info + 'Genome position ' + str(
                    stored_hgvs_not_delins.ac) + ':g.' + str(
                    stored_hgvs_not_delins.posedit.pos.end.base + 1) + ' aligns within a ' + str(
                    self.disparity_deletion_in[1]) + '-bp gap in transcript ' + str(
                    self.tx_hgvs_not_delins.ac)
                self.gapped_transcripts = self.gapped_transcripts + ' ' + str(self.tx_hgvs_not_delins.ac)
                hgvs_refreshed_variant = self.c1_pos_edit(hgvs_genomic)

                # Alignment position
                for_location_c = copy.deepcopy(hgvs_refreshed_variant)
                if 'NM_' in str(for_location_c):
                    for_location_c = self.variant.no_norm_evm.n_to_c(self.tx_hgvs_not_delins)
                gps = for_location_c.posedit.pos.end.base
                gpe = for_location_c.posedit.pos.end.base + 1
                gap_position = ' between positions c.' + str(gps) + '_' + str(gpe) + '\n'
                # Warn update
                self.auto_info = self.auto_info + '%s' % gap_position
            elif '-' in str(self.tx_hgvs_not_delins.posedit.pos.start) and \
                    '-' not in str(self.tx_hgvs_not_delins.posedit.pos.end):
                self.auto_info = self.auto_info + str(stored_hgvs_not_delins.ac) + ':g.' + str(
                    stored_hgvs_not_delins.posedit.pos.start.base) + ' is one of ' + str(
                    self.disparity_deletion_in[
                        1]) + ' genomic base(s) that fail to align to transcript ' + str(
                    self.tx_hgvs_not_delins.ac)
                hgvs_refreshed_variant = self.c2_pos_edit(hgvs_genomic)

                # Alignment position
                for_location_c = copy.deepcopy(hgvs_refreshed_variant)
                if 'NM_' in str(for_location_c):
                    for_location_c = self.variant.no_norm_evm.n_to_c(self.tx_hgvs_not_delins)
                gps = for_location_c.posedit.pos.start.base - 1
                gpe = for_location_c.posedit.pos.start.base
                gap_position = ' between positions c.' + str(gps) + '_' + str(gpe) + '\n'
                # Warn update
                self.auto_info = self.auto_info + '%s' % gap_position
            elif '-' in str(self.tx_hgvs_not_delins.posedit.pos.end) and \
                    '-' not in str(self.tx_hgvs_not_delins.posedit.pos.start):
                self.auto_info = self.auto_info + 'Genome position ' + str(
                    stored_hgvs_not_delins.ac) + ':g.' + str(
                    stored_hgvs_not_delins.posedit.pos.end.base + 1) + ' aligns within a ' + str(
                    self.disparity_deletion_in[1]) + '-bp gap in transcript ' + str(
                    self.tx_hgvs_not_delins.ac)
                self.gapped_transcripts = self.gapped_transcripts + ' ' + str(self.tx_hgvs_not_delins.ac)

                # Have variation in first copy here!
                if running_option == 1:
                    try:
                        c1 = self.validator.vm.n_to_c(self.tx_hgvs_not_delins)
                    except:
                        c1 = self.tx_hgvs_not_delins
                    c2 = copy.deepcopy(c1)
                    c2.posedit.pos.start = c1.posedit.pos.end
                    c2.posedit.pos.end.base = c1.posedit.pos.end.base
                    c2.posedit.pos.end.offset = 0
                    c2.posedit.edit.ref = ''
                    c2.posedit.edit.alt = ''
                    g2 = self.validator.vm.t_to_g(c2, self.variant.hgvs_genomic.ac)
                    c2 = self.validator.vm.g_to_t(g2, c2.ac)
                    reference = c1.posedit.edit.ref + c2.posedit.edit.ref[1:]
                    alternate = c1.posedit.edit.alt + c2.posedit.edit.ref[1:]
                    c3 = copy.deepcopy(c1)
                    c3.posedit.pos.end = c2.posedit.pos.end
                    c3.posedit.edit.ref = ''  # reference
                    c3.posedit.edit.alt = alternate
                    hgvs_refreshed_variant = c3
                else:
                    hgvs_refreshed_variant = self.c1_pos_edit(hgvs_genomic)

                # Alignment position
                for_location_c = copy.deepcopy(hgvs_refreshed_variant)
                if 'NM_' in str(for_location_c):
                    for_location_c = self.variant.no_norm_evm.n_to_c(self.tx_hgvs_not_delins)
                gps = for_location_c.posedit.pos.end.base - 1
                gpe = for_location_c.posedit.pos.end.base
                gap_position = ' between positions c.' + str(gps) + '_' + str(gpe) + '\n'
                # Warn update
                self.auto_info = self.auto_info + '%s' % (gap_position)
            else:
                self.auto_info = self.auto_info + str(stored_hgvs_not_delins.ac) + ':g.' + str(
                    stored_hgvs_not_delins.posedit.pos) + ' contains ' + str(
                    self.disparity_deletion_in[
                        1]) + ' genomic base(s) that fail to align to transcript ' + str(
                    self.tx_hgvs_not_delins.ac) + '\n'

                ## Have variation in second copy here!
                if running_option == 2:
                    self.tx_hgvs_not_delins.posedit.pos.end.base = self.tx_hgvs_not_delins.posedit.pos.start.base + len(
                        self.tx_hgvs_not_delins.posedit.edit.ref) - 1
                elif running_option != 4:
                    self.gapped_transcripts = self.gapped_transcripts + ' ' + str(self.tx_hgvs_not_delins.ac)

                hgvs_refreshed_variant = self.tx_hgvs_not_delins

        return hgvs_refreshed_variant

    def edit_output(self, hgvs_refreshed_variant, saved_hgvs_coding):
        if 'NM_' in str(hgvs_refreshed_variant.ac) and 'c' not in str(hgvs_refreshed_variant.type):
            hgvs_refreshed_variant = self.variant.evm.n_to_c(hgvs_refreshed_variant)

        try:
            hgvs_refreshed_variant = self.variant.hn.normalize(hgvs_refreshed_variant)
            if hgvs_refreshed_variant.posedit.edit.type == 'delins' and \
                    hgvs_refreshed_variant.posedit.edit.ref[-1] == \
                    hgvs_refreshed_variant.posedit.edit.alt[-1]:
                hgvs_refreshed_variant.posedit.edit.ref = hgvs_refreshed_variant.posedit.edit.ref[
                                                          0:-1]
                hgvs_refreshed_variant.posedit.edit.alt = hgvs_refreshed_variant.posedit.edit.alt[
                                                          0:-1]
                hgvs_refreshed_variant.posedit.pos.end.base = hgvs_refreshed_variant.posedit.pos.end.base - 1
                hgvs_refreshed_variant = self.variant.hn.normalize(hgvs_refreshed_variant)
            elif hgvs_refreshed_variant.posedit.edit.type == 'delins' and \
                    hgvs_refreshed_variant.posedit.edit.ref[0] == \
                    hgvs_refreshed_variant.posedit.edit.alt[0]:
                hgvs_refreshed_variant.posedit.edit.ref = hgvs_refreshed_variant.posedit.edit.ref[
                                                          1:]
                hgvs_refreshed_variant.posedit.edit.alt = hgvs_refreshed_variant.posedit.edit.alt[
                                                          1:]
                hgvs_refreshed_variant.posedit.pos.start.base = hgvs_refreshed_variant.posedit.pos.start.base + 1
                hgvs_refreshed_variant = self.variant.hn.normalize(hgvs_refreshed_variant)
        except Exception as e:
            error = str(e)
            # Ensure the final variant is not intronic nor does it cross exon boundaries
            if 'Normalization of intronic variants is not supported' in error or \
                    'Unsupported normalization of variants spanning the exon-intron boundary' in error:
                hgvs_refreshed_variant = saved_hgvs_coding

        return hgvs_refreshed_variant

    def logic_check(self, hgvs_not_delins, rn_tx_hgvs_not_delins, hgvs_coding, do_continue=False, offset_check=False):
        # Logic
        if len(hgvs_not_delins.posedit.edit.ref) < len(rn_tx_hgvs_not_delins.posedit.edit.ref):
            gap_length = len(rn_tx_hgvs_not_delins.posedit.edit.ref) - len(hgvs_not_delins.posedit.edit.ref)
            self.disparity_deletion_in = ['chromosome', gap_length]
        elif len(hgvs_not_delins.posedit.edit.ref) > len(rn_tx_hgvs_not_delins.posedit.edit.ref):
            gap_length = len(hgvs_not_delins.posedit.edit.ref) - len(rn_tx_hgvs_not_delins.posedit.edit.ref)
            self.disparity_deletion_in = ['transcript', gap_length]
        else:
            re_capture_tx_variant = []
            for internal_possibility in self.hgvs_genomic_possibilities:
                if internal_possibility == '':
                    continue

                hgvs_t_possibility = self.validator.vm.g_to_t(internal_possibility, hgvs_coding.ac)
                if hgvs_t_possibility.posedit.edit.type == 'ins':
                    try:
                        hgvs_t_possibility = self.validator.vm.c_to_n(hgvs_t_possibility)
                    except:
                        if do_continue:
                            continue
                        fn.exceptPass()
                    if offset_check:
                        if hgvs_t_possibility.posedit.pos.start.offset != 0 or \
                                hgvs_t_possibility.posedit.pos.end.offset != 0:
                            continue
                    ins_ref = self.validator.sf.fetch_seq(hgvs_t_possibility.ac,
                                                          hgvs_t_possibility.posedit.pos.start.base - 1,
                                                          hgvs_t_possibility.posedit.pos.start.base + 1)
                    try:
                        hgvs_t_possibility = self.validator.vm.n_to_c(hgvs_t_possibility)
                    except:
                        if do_continue:
                            continue
                        fn.exceptPass()
                    hgvs_t_possibility.posedit.edit.ref = ins_ref
                    hgvs_t_possibility.posedit.edit.alt = ins_ref[
                                                              0] + hgvs_t_possibility.posedit.edit.alt + ins_ref[1]
                if internal_possibility.posedit.edit.type == 'ins':
                    ins_ref = self.validator.sf.fetch_seq(internal_possibility.ac,
                                                          internal_possibility.posedit.pos.start.base - 1,
                                                          internal_possibility.posedit.pos.end.base)
                    internal_possibility.posedit.edit.ref = ins_ref
                    internal_possibility.posedit.edit.alt = ins_ref[
                                                                0] + internal_possibility.posedit.edit.alt + ins_ref[1]

                if len(hgvs_t_possibility.posedit.edit.ref) < len(internal_possibility.posedit.edit.ref):
                    gap_length = len(internal_possibility.posedit.edit.ref) - len(hgvs_t_possibility.posedit.edit.ref)
                    re_capture_tx_variant = ['transcript', gap_length, hgvs_t_possibility]
                    hgvs_not_delins = internal_possibility
                    self.hgvs_genomic_5pr = internal_possibility
                    break

            if re_capture_tx_variant:
                try:
                    self.tx_hgvs_not_delins = self.validator.vm.c_to_n(re_capture_tx_variant[2])
                except:
                    self.tx_hgvs_not_delins = re_capture_tx_variant[2]
                self.disparity_deletion_in = re_capture_tx_variant[0:-1]

        return hgvs_not_delins

    def get_hgvs_seek_var(self, hgvs_genomic, hgvs_coding, ori=None, with_query_genomic=False):
        if not ori:
            ori = self.orientation

        if ori == -1:
            try:
                query_genomic = self.variant.reverse_normalizer.normalize(hgvs_genomic)
            except:
                query_genomic = hgvs_genomic
        else:
            # position genomic at its most 3 prime position
            try:
                query_genomic = self.variant.hn.normalize(hgvs_genomic)
            except:
                query_genomic = hgvs_genomic

        # Normalise intronic, if called with query_genomic
        if with_query_genomic:
            if hgvs_coding.posedit.pos.start.offset != 0:
                hgvs_coding = self.variant.evm.g_to_t(query_genomic, hgvs_coding.ac)

        # Map to the transcript and test for movement
        try:
            hgvs_seek_var = self.variant.evm.g_to_t(query_genomic, hgvs_coding.ac)
        except hgvs.exceptions.HGVSError:
            hgvs_seek_var = hgvs_coding

        if with_query_genomic:
            return hgvs_seek_var, query_genomic, hgvs_coding

        return hgvs_seek_var

    def rev_norm_ins(self, hgvs_coding, hgvs_genomic):
        # direct mapping from reverse_normalized transcript insertions in the delins format
        try:
            if hgvs_coding.posedit.edit.type == 'ins':
                most_5pr_hgvs_transcript_variant = copy.deepcopy(hgvs_coding)
                most_3pr_hgvs_transcript_variant = self.variant.reverse_normalizer.normalize(hgvs_coding)
                try:
                    n_3pr = self.validator.vm.c_to_n(most_3pr_hgvs_transcript_variant)
                    n_5pr = self.validator.vm.c_to_n(most_5pr_hgvs_transcript_variant)
                except:
                    n_3pr = most_3pr_hgvs_transcript_variant
                    n_5pr = most_5pr_hgvs_transcript_variant
                # Make into a delins by adding the ref bases to the variant ref and alt
                pr3_ref = self.validator.sf.fetch_seq(hgvs_coding.ac, n_3pr.posedit.pos.start.base - 1,
                                                      n_3pr.posedit.pos.end.base)
                pr5_ref = self.validator.sf.fetch_seq(hgvs_coding.ac, n_5pr.posedit.pos.start.base - 1,
                                                      n_5pr.posedit.pos.end.base)
                most_3pr_hgvs_transcript_variant.posedit.edit.ref = pr3_ref
                most_5pr_hgvs_transcript_variant.posedit.edit.ref = pr5_ref
                most_3pr_hgvs_transcript_variant.posedit.edit.alt = pr3_ref[0] + \
                    most_3pr_hgvs_transcript_variant.posedit.edit.alt + pr3_ref[1]
                most_5pr_hgvs_transcript_variant.posedit.edit.alt = pr5_ref[0] + \
                    most_5pr_hgvs_transcript_variant.posedit.edit.alt + pr5_ref[1]
                # Map to the genome
                genomic_from_most_3pr_hgvs_transcript_variant = self.validator.vm.t_to_g(
                    most_3pr_hgvs_transcript_variant, hgvs_genomic.ac)
                genomic_from_most_5pr_hgvs_transcript_variant = self.validator.vm.t_to_g(
                    most_5pr_hgvs_transcript_variant, hgvs_genomic.ac)

                # Normalize - If the variant spans a gap it should then form a static genomic variant
                try:
                    genomic_from_most_3pr_hgvs_transcript_variant = self.variant.hn.normalize(
                        genomic_from_most_3pr_hgvs_transcript_variant)
                except hgvs.exceptions.HGVSInvalidVariantError as e:
                    error = str(e)
                    if error == 'base start position must be <= end position':
                        start = genomic_from_most_3pr_hgvs_transcript_variant.posedit.pos.start.base
                        end = genomic_from_most_3pr_hgvs_transcript_variant.posedit.pos.end.base
                        genomic_from_most_3pr_hgvs_transcript_variant.posedit.pos.start.base = end
                        genomic_from_most_3pr_hgvs_transcript_variant.posedit.pos.end.base = start
                        genomic_from_most_3pr_hgvs_transcript_variant = self.variant.hn.normalize(
                            genomic_from_most_3pr_hgvs_transcript_variant)
                try:
                    genomic_from_most_5pr_hgvs_transcript_variant = self.variant.hn.normalize(
                        genomic_from_most_5pr_hgvs_transcript_variant)
                except hgvs.exceptions.HGVSInvalidVariantError as e:
                    error = str(e)
                    if error == 'base start position must be <= end position':
                        start = genomic_from_most_5pr_hgvs_transcript_variant.posedit.pos.start.base
                        end = genomic_from_most_5pr_hgvs_transcript_variant.posedit.pos.end.base
                        genomic_from_most_5pr_hgvs_transcript_variant.posedit.pos.start.base = end
                        genomic_from_most_5pr_hgvs_transcript_variant.posedit.pos.end.base = start
                        genomic_from_most_5pr_hgvs_transcript_variant = self.variant.hn.normalize(
                            genomic_from_most_5pr_hgvs_transcript_variant)

                try:
                    if genomic_from_most_3pr_hgvs_transcript_variant.posedit.edit.alt is None:
                        genomic_from_most_3pr_hgvs_transcript_variant.posedit.edit.alt = ''
                except Exception as e:
                    if str(e) == "'Dup' object has no attribute 'alt'":
                        genomic_from_most_3pr_hgvs_transcript_variant_delins_from_dup = fn.hgvs_dup2indel(
                            genomic_from_most_3pr_hgvs_transcript_variant)
                        genomic_from_most_3pr_hgvs_transcript_variant = self.validator.hp.parse_hgvs_variant(
                            genomic_from_most_3pr_hgvs_transcript_variant_delins_from_dup)

                try:
                    if most_3pr_hgvs_transcript_variant.posedit.edit.alt is None:
                        most_3pr_hgvs_transcript_variant.posedit.edit.alt = ''
                except Exception as e:
                    if str(e) == "'Dup' object has no attribute 'alt'":
                        most_3pr_hgvs_transcript_variant_delins_from_dup = fn.hgvs_dup2indel(
                            most_3pr_hgvs_transcript_variant)
                        most_3pr_hgvs_transcript_variant = self.validator.hp.parse_hgvs_variant(
                            most_3pr_hgvs_transcript_variant_delins_from_dup)

                try:
                    if genomic_from_most_5pr_hgvs_transcript_variant.posedit.edit.alt is None:
                        genomic_from_most_5pr_hgvs_transcript_variant.posedit.edit.alt = ''
                except Exception as e:
                    if str(e) == "'Dup' object has no attribute 'alt'":
                        genomic_from_most_5pr_hgvs_transcript_variant_delins_from_dup = fn.hgvs_dup2indel(
                            genomic_from_most_5pr_hgvs_transcript_variant)
                        genomic_from_most_5pr_hgvs_transcript_variant = self.validator.hp.parse_hgvs_variant(
                            genomic_from_most_5pr_hgvs_transcript_variant_delins_from_dup)

                try:
                    if most_5pr_hgvs_transcript_variant.posedit.edit.alt is None:
                        most_5pr_hgvs_transcript_variant.posedit.edit.alt = ''
                except Exception as e:
                    if str(e) == "'Dup' object has no attribute 'alt'":
                        most_5pr_hgvs_transcript_variant_delins_from_dup = fn.hgvs_dup2indel(
                            most_5pr_hgvs_transcript_variant)
                        most_5pr_hgvs_transcript_variant = self.validator.hp.parse_hgvs_variant(
                            most_5pr_hgvs_transcript_variant_delins_from_dup)

                if len(genomic_from_most_3pr_hgvs_transcript_variant.posedit.edit.alt) < len(
                        most_3pr_hgvs_transcript_variant.posedit.edit.alt):
                    self.hgvs_genomic_possibilities.append(genomic_from_most_3pr_hgvs_transcript_variant)
                if len(genomic_from_most_5pr_hgvs_transcript_variant.posedit.edit.alt) < len(
                        most_5pr_hgvs_transcript_variant.posedit.edit.alt):
                    self.hgvs_genomic_possibilities.append(genomic_from_most_5pr_hgvs_transcript_variant)

        except hgvs.exceptions.HGVSUnsupportedOperationError as e:
            fn.exceptPass()
