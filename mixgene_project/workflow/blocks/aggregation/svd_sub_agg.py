__author__ = 'pavel'


from webapp.tasks import wrapper_task
from workflow.blocks.blocks_pallet import GroupType
from workflow.blocks.fields import ActionsList, ActionRecord, InputBlockField, ParamField, InputType, FieldType, \
    OutputBlockField
from workflow.blocks.generic import GenericBlock, execute_block_actions_list
from wrappers.aggregation.aggregation import aggregation_task


class SvdSubAgg(GenericBlock):
    is_abstract = True
    block_group = GroupType.AGGREGATION

    is_block_supports_auto_execution = True

    _block_actions = ActionsList([
        ActionRecord("save_params", ["created", "valid_params", "done", "ready"], "validating_params",
                     user_title="Save parameters"),
        ActionRecord("on_params_is_valid", ["validating_params"], "ready"),
        ActionRecord("on_params_not_valid", ["validating_params"], "created"),
        ])
    _block_actions.extend(execute_block_actions_list)

    _mRNA_es = InputBlockField(name="mRNA_es", order_num=10,
                               required_data_type="ExpressionSet", required=True)
    _miRNA_es = InputBlockField(name="miRNA_es", order_num=20,
                                required_data_type="ExpressionSet", required=True)
    _interaction = InputBlockField(name="interaction", order_num=30,
                                   required_data_type="BinaryInteraction", required=True)

    c = ParamField(name="c", title="Constant c",
                   input_type=InputType.TEXT, field_type=FieldType.FLOAT, init_val=1.0)

    agg_es = OutputBlockField(name="agg_es", provided_data_type="ExpressionSet")

    mode = ""

    def __init__(self, *args, **kwargs):
        super(SvdSubAgg, self).__init__(*args, **kwargs)
        self.celery_task = None

    def execute(self, exp, *args, **kwargs):
        self.clean_errors()
        mRNA_es = self.get_input_var("mRNA_es")
        miRNA_es = self.get_input_var("miRNA_es")
        interaction_matrix = self.get_input_var("interaction")

        self.celery_task = wrapper_task.s(
            aggregation_task,
            exp, self,
            mode=self.mode,
            c=self.c,
            m_rna_es=mRNA_es,
            mi_rna_es=miRNA_es,
            interaction_matrix=interaction_matrix,
            base_filename="%s_%s_agg" % (self.uuid, self.mode)
        )
        exp.store_block(self)
        self.celery_task.apply_async()

    def success(self, exp, agg_es):
        self.set_out_var("agg_es", agg_es)
        exp.store_block(self)


class SubAggregation(SvdSubAgg):
    block_base_name = "SUB_AGG"
    name = "Subtractive miRNA-aggregation"
    mode = "SUB"


class SvdAggregation(SvdSubAgg):
    block_base_name = "SVD_AGG"
    name = "SVD-based miRNA-aggregation"
    mode = "SVD"
