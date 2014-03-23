# -*- coding: utf-8 -*-
from abc import abstractmethod
import logging
import rpy2.robjects as R
import pandas.rpy.common as com
import numpy as np
import pandas as pd

from mixgene.util import log_timing, stopwatch
from environment.structures import TableResult
from webapp.models import Experiment

from webapp.tasks import wrapper_task
from workflow.blocks.fields import FieldType, BlockField, OutputBlockField, InputBlockField, InputType, ParamField, \
    ActionRecord, ActionsList

from workflow.blocks.generic import GenericBlock, save_params_actions_list, execute_block_actions_list

from wrappers.aggregation import aggregation_task

log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)


from django.conf import settings
R_LIB_CUSTOM_PATH = settings.R_LIB_CUSTOM_PATH
#R.r['library']("miXGENE", lib_loc=R_LIB_CUSTOM_PATH)


def apply_ranking(
        exp, block,
        es, ranking_name,
        result_table,
        pheno_class_column=None, options=None
):
    if not options:
        options = {}
    if not pheno_class_column:
        pheno_class_column = es.pheno_metadata["user_class_title"]

    R.r['source'](R_LIB_CUSTOM_PATH + '/ranking.Methods.r')
    func = R.r[ranking_name]

    assay_df = es.get_assay_data_frame()
    x = com.convert_to_r_matrix(assay_df)
    y = es.get_pheno_column_as_r_obj(pheno_class_column)

    with stopwatch(name="Computing ranking: `%s` options: `%s`" % (ranking_name, options),
                   threshold=0.01):
        ranking_list = list(func(R.r['t'](x), y, **options))

    ranking_fixed = map(lambda a: a - 1, ranking_list)

    feature_names = np.array(assay_df.index)
    df = pd.DataFrame(index=feature_names[ranking_fixed],
                      data=range(len(ranking_list)),
                      columns=["rank"])

    result_table.store_table(df)
    return [result_table], {}


class GenericRankingBlock(GenericBlock):
    block_base_name = ""
    is_block_supports_auto_execution = True

    _block_actions = ActionsList([
        ActionRecord("save_params", ["created", "valid_params", "done", "ready"], "validating_params",
                     user_title="Save parameters"),
        ActionRecord("on_params_is_valid", ["validating_params"], "ready"),
        ActionRecord("on_params_not_valid", ["validating_params"], "created"),
    ])
    _block_actions.extend(execute_block_actions_list)

    _es = InputBlockField(
        name="es", order_num=10,
        required_data_type="ExpressionSet", required=True
    )

    best = ParamField(
        name="best", title="Consider only best",
        input_type=InputType.TEXT,
        field_type=FieldType.INT, init_val=None
    )

    def __init__(self, *args, **kwargs):
        super(GenericRankingBlock, self).__init__(*args, **kwargs)
        self.ranking_name = None
        self.ranking_options = {}
        self.celery_task = None

        exp = Experiment.get_exp_by_id(self.exp_id)
        self.result = TableResult(
            base_dir=exp.get_data_folder(),
            base_filename="%s_gt_result" % self.uuid,
        )

    def collect_options(self):
        pass

    def execute(self, exp, *args, **kwargs):
        self.clean_errors()
        self.collect_options()

        self.celery_task = wrapper_task.s(
            apply_ranking,
            exp=exp, block=self,
            es=self.get_input_var("es"),
            ranking_name=self.ranking_name,
            result_table=self.result,
            options=self.ranking_options
        )
        exp.store_block(self)
        self.celery_task.apply_async()
        log.debug("Sent ranking computation to queue")

    def success(self, exp, result, *args, **kwargs):
        self.result = result
        self.set_out_var("result", self.result)
        exp.store_block(self)


class SvmrfeRanking(GenericRankingBlock):
    block_base_name = "SVMRFE_RANK"

    def __init__(self, *args, **kwargs):
        super(SvmrfeRanking, self).__init__("SVMRFE ranking", *args, **kwargs)
        self.ranking_name = "SVMRFE"
        self.result.headers = ["rank"]


class SvmrfeRestrictedRanking(GenericRankingBlock):
    block_base_name = "RESTR_SVMRFE_RANK"

    def __init__(self, *args, **kwargs):
        super(SvmrfeRestrictedRanking, self).__init__("Restricted SVMRFE ranking", *args, **kwargs)
        self.ranking_name = "RestrictedSVMRFE"
        self.result.headers = ["rank"]

    def collect_options(self):
        if hasattr(self, "best"):
            try:
                best = int(self.best)
                if best > 0:
                    self.ranking_options["best"] = best
            except:
                pass


class TTestRanking(GenericRankingBlock):
    block_base_name = "TTEST_RANK"

    def __init__(self, *args, **kwargs):
        super(TTestRanking, self).__init__("TTest ranking", *args, **kwargs)
        self.ranking_name = "TTestRanking"
        self.result.headers = ["rank"]

    def collect_options(self):
        if hasattr(self, "best"):
            try:
                best = int(self.best)
                if best > 0:
                    self.ranking_options["best"] = best
            except:
                pass


class RandomRanking(GenericRankingBlock):
    block_base_name = "RANDOM_RANK"

    def __init__(self, *args, **kwargs):
        super(RandomRanking, self).__init__("Random ranking", *args, **kwargs)
        self.ranking_name = "RandomRanking"
        self.result.headers = ["rank"]

    def collect_options(self):
        if hasattr(self, "best"):
            try:
                best = int(self.best)
                if best > 0:
                    self.ranking_options["best"] = best
            except:
                pass
