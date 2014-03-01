# -*- coding: utf-8 -*-

import pandas as pd

from workflow.blocks.generic import GenericBlock, ActionsList, save_params_actions_list, BlockField, FieldType, \
    ActionRecord, ParamField, InputType, execute_block_actions_list, OutputBlockField, InputBlockField

from converters.gene_set_tools import map_gene_sets_to_probes
from workflow.common_tasks import wrapper_task


def merge_two_es(exp, block,
                 es_1, es_2,
                 base_filename):
    """
        @type es_1: ExpressionSet
        @type es_2: ExpressionSet
    """
    merged_es = es_1.clone(base_filename)
    merged_es.store_pheno_data_frame(es_1.get_pheno_data_frame())

    assay_df_1 = es_1.get_assay_data_frame()
    assay_df_2 = es_2.get_assay_data_frame()

    merged_assay_df = pd.concat([assay_df_1, assay_df_2])
    merged_es.store_assay_data_frame(merged_assay_df)

    return [merged_es], {}


class MergeExpressionSets(GenericBlock):
    block_base_name = "MergeES"
    is_block_supports_auto_execution = True

    _block_actions = ActionsList([
        ActionRecord("save_params", ["created", "valid_params", "done", "ready"], "validating_params",
                     user_title="Save parameters"),
        ActionRecord("on_params_is_valid", ["validating_params"], "ready"),
        ActionRecord("on_params_not_valid", ["validating_params"], "created"),
        ])
    _block_actions.extend(execute_block_actions_list)

    _es_1 = InputBlockField(name="es_1", title="Set 1", required_data_type="ExpressionSet", required=True)
    _es_2 = InputBlockField(name="es_2", title="Set 2", required_data_type="ExpressionSet", required=True)

    merged_es = OutputBlockField(name="merged_es", provided_data_type="ExpressionSet")

    def __init__(self, *args, **kwargs):
        super(MergeExpressionSets, self).__init__(
            "Merge two expression by samples", *args, **kwargs)
        self.celery_task = None

    def execute(self, exp, *args, **kwargs):
        self.clean_errors()
        # import ipdb; ipdb.set_trace()
        self.celery_task = wrapper_task.s(
            merge_two_es,
            exp, self,
            es_1 = self.get_input_var("es_1"),
            es_2 = self.get_input_var("es_2"),
            base_filename="%s_merged" % self.uuid,
        )
        exp.store_block(self)
        self.celery_task.apply_async()

    def success(self, exp, es):
        self.set_out_var("merged_es", es)
        exp.store_block(self)