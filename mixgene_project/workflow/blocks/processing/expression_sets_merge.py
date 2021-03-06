# -*- coding: utf-8 -*-

import pandas as pd
from webapp.tasks import wrapper_task
from workflow.blocks.blocks_pallet import GroupType
from workflow.blocks.fields import FieldType, BlockField, OutputBlockField, InputBlockField, InputType, ParamField, \
    ActionRecord, ActionsList

from workflow.blocks.generic import GenericBlock, save_params_actions_list, execute_block_actions_list

from converters.gene_set_tools import map_gene_sets_to_probes
from django.conf import settings

def merge_two_es(exp, block,
                 es_1, es_2, con,
                 base_filename):
    """
        @type es_1: ExpressionSet
        @type es_2: ExpressionSet
    """
    if settings.CELERY_DEBUG:
        import sys
        sys.path.append('/Migration/skola/phd/projects/miXGENE/mixgene_project/wrappers/pycharm-debug.egg')
        import pydevd
        pydevd.settrace('localhost', port=6901, stdoutToServer=True, stderrToServer=True)

    merged_es = es_1.clone(base_filename)
    try:
        merged_es.store_pheno_data_frame(es_1.get_pheno_data_frame())
    except RuntimeError as e:
        pass
    axis = 0
    assay_df_1 = es_1.get_assay_data_frame()
    assay_df_2 = es_2.get_assay_data_frame()
    if con == "CC":
        axis = 1
    merged_assay_df = pd.concat([assay_df_1, assay_df_2], axis=axis)
    merged_es.store_assay_data_frame(merged_assay_df)

    return [merged_es], {}


class MergeExpressionSets(GenericBlock):
    block_base_name = "MergeES"
    name = "Concatenate Expression"
    block_group = GroupType.PROCESSING

    is_block_supports_auto_execution = True

    _block_actions = ActionsList([
        ActionRecord("save_params", ["created", "valid_params", "done", "ready"], "validating_params",
                     user_title="Save parameters"),
        ActionRecord("on_params_is_valid", ["validating_params"], "ready"),
        ActionRecord("on_params_not_valid", ["validating_params"], "created"),
        ])
    _block_actions.extend(execute_block_actions_list)

    _es_1 = InputBlockField(name="es_1", title="Set 1", order_num=10,
                            required_data_type="ExpressionSet", required=True)
    _es_2 = InputBlockField(name="es_2", title="Set 2", order_num=20,
                            required_data_type="ExpressionSet", required=True)
    _es_matrix_con = ParamField(
        "_es_matrix_con", title="Concatenation", order_num=30,
        input_type=InputType.SELECT, field_type=FieldType.STR,
        init_val="CR",
        options={
            "inline_select_provider": True,
            "select_options": [
                ["CR", "concatenate samples"],
                ["CC", "concatenate features"]
            ]
        }
    )
    merged_es = OutputBlockField(name="merged_es", provided_data_type="ExpressionSet")

    def __init__(self, *args, **kwargs):
        super(MergeExpressionSets, self).__init__(*args, **kwargs)
        self.celery_task = None

    def execute(self, exp, *args, **kwargs):
        self.clean_errors()
        con = getattr(self, "_es_matrix_con", "CR")
        # import ipdb; ipdb.set_trace()
        self.celery_task = wrapper_task.s(
            merge_two_es,
            exp, self,
            es_1 = self.get_input_var("es_1"),
            es_2 = self.get_input_var("es_2"),
            con = con,
            base_filename="%s_merged" % self.uuid,
        )
        exp.store_block(self)
        self.celery_task.apply_async()

    def success(self, exp, es):
        self.set_out_var("merged_es", es)
        exp.store_block(self)
