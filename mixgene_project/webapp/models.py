from __builtin__ import staticmethod
from collections import defaultdict
import os
import shutil
import cPickle as pickle
import hashlib

from django.db import models
from django.contrib.auth.models import User
from redis.client import StrictPipeline

from mixgene.settings import MEDIA_ROOT
from mixgene.util import get_redis_instance
from mixgene.redis_helper import ExpKeys
from mixgene.util import dyn_import
from environment.structures import GmtStorage, GeneSets
from webapp.scope import Scope, ScopeRunner
from workflow.execution import ScopeState
from webapp.scope import auto_exec_task

class CachedFile(models.Model):
    uri = models.TextField(default="")
    uri_sha = models.CharField(max_length=127, default="")
    dt_updated = models.DateTimeField(auto_now=True)

    def __unicode__(self):
        return u"cached file of %s, updated at %s" % (self.uri, self.dt_updated)

    def get_file_path(self):
        return '/'.join(map(str, [MEDIA_ROOT, 'data', 'cache', self.uri_sha]))

    def save(self, *args, **kwargs):
        self.uri_sha = hashlib.sha256(self.uri).hexdigest()
        super(CachedFile, self).save(*args, **kwargs)

    @staticmethod
    def update_cache(uri, path_to_real_file):
        res = CachedFile.objects.filter(uri=uri)
        if len(res) == 0:
            cf = CachedFile()
            cf.uri = uri
            cf.save()
        else:
            cf = res[0]

        shutil.copy(path_to_real_file, cf.get_file_path())

    @staticmethod
    def look_up(uri):
        res = CachedFile.objects.filter(uri=uri)
        if len(res) == 0:
            return None
        else:
            return res[0]


class Experiment(models.Model):
    author = models.ForeignKey(User)

    # Obsolete
    status = models.TextField(default="created")

    dt_created = models.DateTimeField(auto_now_add=True)
    dt_updated = models.DateTimeField(auto_now=True)


    def __unicode__(self):
        return u"%s" % self.pk

    def __init__(self, *args, **kwargs):
        super(Experiment, self).__init__(*args, **kwargs)
        self._blocks_grouped_by_provided_type = None

    @staticmethod
    def get_exp_by_ctx(ctx):
        return Experiment.objects.get(pk=ctx["exp_id"])

    @staticmethod
    def get_exp_by_id(_pk):
        return Experiment.objects.get(pk=_pk)

    def execute(self):
        auto_exec_task.s(self, "root").apply_async()

    def init_ctx(self, ctx, redis_instance=None):
        ## TODO: RENAME TO init experiment and invoke on first save
        if redis_instance is None:
            r = get_redis_instance()
        else:
            r = redis_instance

        key_context = ExpKeys.get_context_store_key(self.pk)
        key_context_version = ExpKeys.get_context_version_key(self.pk)

        pipe = r.pipeline()

        # FIXME: replace with MSET
        pipe.set(key_context, pickle.dumps(ctx))
        pipe.set(key_context_version, 0)

        pipe.hset(ExpKeys.get_scope_creating_block_uuid_keys(self.pk), "root", None)

        pipe.sadd(ExpKeys.get_all_exp_keys_key(self.pk),
                  [key_context,
                   key_context_version,
                   ExpKeys.get_exp_blocks_list_key(self.pk),
                   ExpKeys.get_blocks_uuid_by_alias(self.pk),
                   ExpKeys.get_scope_vars_keys(self.pk),
                   ExpKeys.get_scope_creating_block_uuid_keys(self.pk),
                   ExpKeys.get_scope_key(self.pk, "root")
        ])

        pipe.execute()

    def get_ctx(self, redis_instance=None):
        if redis_instance is None:
            r = get_redis_instance()
        else:
            r = redis_instance

        key_context = ExpKeys.get_context_store_key(self.pk)
        pickled_ctx = r.get(key_context)
        if pickled_ctx is not None:
            ctx = pickle.loads(pickled_ctx)
        else:
            raise KeyError("Context wasn't found for exp_id: %s" % self.pk)
        return ctx

    def update_ctx(self, new_ctx, redis_instance=None):
        if redis_instance is None:
            r = get_redis_instance()
        else:
            r = redis_instance

        key_context = ExpKeys.get_context_store_key(self.pk)
        key_context_version = ExpKeys.get_context_version_key(self.pk)

        result = None
        lua = """
        local ctx_version = tonumber(ARGV[1])
        local actual_version = redis.call('GET', KEYS[1])
        actual_version = tonumber(actual_version)
        local result = "none"
        if ctx_version == actual_version then
            redis.call('SET', KEYS[1], actual_version + 1)
            redis.call('SET', KEYS[2], ARGV[2])
            result = "ok"
        else
            result = "fail"
        end
        return result
        """
        safe_update = r.register_script(lua)
        # TODO: checkpoint for repeat if lua check version fails
        retried = 0
        while result != "ok" and retried < 4:
            retried = 1
            ctx_version, pickled_ctx = r.mget(key_context_version, key_context)
            if pickled_ctx is not None:
                ctx = pickle.loads(pickled_ctx)
            else:
                raise KeyError("Context wasn't found for exp_id: %s" % self.pk)

            ctx.update(new_ctx)
            # TODO: move lua to dedicated module or singletone load in redis helper
            #  keys: ctx_version_key, ctx_key
            #  args: ctx_version,     ctx

            result = safe_update(
                keys=[key_context_version, key_context],
                args=[ctx_version, pickle.dumps(ctx)])

        if result != "ok":
            raise Exception("Failed to update context")

    def get_data_folder(self):
        return '/'.join(map(str, [MEDIA_ROOT, 'data', self.author.id, self.pk]))

    def get_data_file_path(self, filename, file_extension="csv"):
        if file_extension is not None:
            return self.get_data_folder() + "/" + filename + "." + file_extension
        else:
            return self.get_data_folder() + "/" + filename

    def validate(self, request):
        self.update_ctx({})
        self.save()

    def get_all_scopes_with_block_uuids(self, redis_instance=None):
        if redis_instance is None:
            r = get_redis_instance()
        else:
            r = redis_instance

        return r.hgetall(ExpKeys.get_scope_creating_block_uuid_keys(self.pk))

    def store_block(self, block, new_block=False, redis_instance=None, dont_execute_pipe=False):
        if redis_instance is None:
            r = get_redis_instance()
        else:
            r = redis_instance

        if not isinstance(r, StrictPipeline):
            pipe = r.pipeline()
        else:
            pipe = r

        block_key = ExpKeys.get_block_key(block.uuid)
        if new_block:
            pipe.rpush(ExpKeys.get_exp_blocks_list_key(self.pk), block.uuid)
            pipe.sadd(ExpKeys.get_all_exp_keys_key(self.pk), block_key)
            pipe.hset(ExpKeys.get_blocks_uuid_by_alias(self.pk), block.base_name, block.uuid)

            # # TODO: refactor to scope.py
            # for var_name, data_type in block.provided_output.iteritems():
            #     self.register_variable(block.scope, block.uuid, var_name, data_type, pipe)

            if block.create_new_scope:
                #import ipdb; ipdb.set_trace()
                # for var_name, data_type in block.provided_objects_inner.iteritems():
                #     self.register_variable(block.sub_scope, block.uuid, var_name, data_type, pipe)

                pipe.hset(ExpKeys.get_scope_creating_block_uuid_keys(self.pk),
                          block.sub_scope_name, block.uuid)

            if block.scope_name != "root":
                # need to register in parent block
                parent_uuid = r.hget(ExpKeys.get_scope_creating_block_uuid_keys(self.pk), block.scope_name)
                #import ipdb; ipdb.set_trace()
                print r.hgetall(ExpKeys.get_scope_creating_block_uuid_keys(self.pk)), block.scope_name
                parent = self.get_block(parent_uuid, r)
                #import ipdb; ipdb.set_trace()

                # TODO: remove code dependency here
                parent.children_blocks.append(block.uuid)
                self.store_block(parent,
                                 new_block=False,
                                 redis_instance=pipe,
                                 dont_execute_pipe=True)

        pipe.set(block_key, pickle.dumps(block))

        if not dont_execute_pipe:
            pipe.execute()

        print "block %s was stored with state: %s" % (block.uuid, block.state)

    def change_block_alias(self, block, new_base_name):
        r = get_redis_instance()

        key = ExpKeys.get_blocks_uuid_by_alias(self.pk)
        pipe = r.pipeline()
        pipe.hdel(key, block.base_name)
        pipe.hset(key, new_base_name, block.uuid)
        pipe.execute()
        block.base_name = new_base_name
        self.store_block(block, redis_instance=r)

    @staticmethod
    def get_exp_from_request(request):
        exp_id = int(request.POST['exp_id'])
        return Experiment.objects.get(pk=exp_id)

    def get_block_by_alias(self, alias, redis_instance=None):
        """
            @type  alias: str
            @param alias: Human readable block name, can be altered

            @type  redis_instance: Redis
            @param redis_instance: Instance of redis client

            @rtype: GenericBlock
            @return: Block instance
        """
        if redis_instance is None:
            r = get_redis_instance()
        else:
            r = redis_instance

        uuid = r.hget(ExpKeys.get_blocks_uuid_by_alias(self.pk), alias)
        return self.get_block(uuid, r)

    @staticmethod
    def get_block(block_uuid, redis_instance=None):
        """
            @type  block_uuid: str
            @param block_uuid: Block instance identifier

            @type  redis_instance: Redis
            @param redis_instance: Instance of redis client

            @rtype: GenericBlock
            @return: Block instance
        """
        if redis_instance is None:
            r = get_redis_instance()
        else:
            r = redis_instance

        return pickle.loads(r.get(ExpKeys.get_block_key(block_uuid)))

    def get_scope_var_value(self, scope_var, redis_instance=None):
        """
            @type scope_var: webapp.scope.ScopeVar
        """
        if redis_instance is None:
            r = get_redis_instance()
        else:
            r = redis_instance

        block = self.get_block(scope_var.block_uuid, r)
        return block.get_out_var(scope_var.var_name)

    @staticmethod
    def get_blocks(block_uuid_list, redis_instance=None):
        """
            @type  block_uuid_list: list
            @param block_uuid_list: List of Block instance identifier

            @type  redis_instance: Redis
            @param redis_instance: Instance of redis client

            @rtype: GenericBlock
            @return: Block instance
        """
        if redis_instance is None:
            r = get_redis_instance()
        else:
            r = redis_instance

        return [(uuid, pickle.loads(r.get(ExpKeys.get_block_key(uuid))))
                for uuid in block_uuid_list]

    def group_blocks_by_provided_type(self, included_inner_blocks=None, redis_instance=None):
        if self._blocks_grouped_by_provided_type is not None:
            return self._blocks_grouped_by_provided_type
        if redis_instance is None:
            r = get_redis_instance()
        else:
            r = redis_instance

        uuid_list = self.get_all_block_uuids(included_inner_blocks, r);

        self._blocks_grouped_by_provided_type = defaultdict(list)
        for uuid in uuid_list:
            block = self.get_block(uuid, r)
            provided = block.get_provided_objects()
            for data_type, field_name in provided.iteritems():
                self._blocks_grouped_by_provided_type[data_type].append(
                    (uuid, block.base_name, field_name)
                )
        return self._blocks_grouped_by_provided_type

    def get_all_block_uuids(self, redis_instance=None):
        """
        @type included_inner_blocks: list of str
        @param included_inner_blocks: uuids of inner blocks to be included

        @param redis_instance: Redis client

        @return: list of block uuids
        """
        if redis_instance is None:
            r = get_redis_instance()
        else:
            r = redis_instance

        return r.lrange(ExpKeys.get_exp_blocks_list_key(self.pk), 0, -1) or []

    def get_block_aliases_map(self, redis_instance=None):
        """
        @param redis_instance: Redis

        @return: Map { uuid -> alias }
        @rtype: dict
        """
        if redis_instance is None:
            r = get_redis_instance()
        else:
            r = redis_instance

        orig_map = r.hgetall(ExpKeys.get_blocks_uuid_by_alias(self.pk))
        return dict([
            (uuid, alias)
            for alias, uuid in orig_map.iteritems()
        ])

    def build_block_dependencies_by_scope(self, scope_name):
        """
            @return: { block: [ dependencies] }, root blocks have empty list as dependency
        """
        dependencies = {}
        # TODO: store in redis block uuids by scope
        for uuid, block in self.get_blocks(self.get_all_block_uuids()):
            if block.scope_name != scope_name:
                continue
            else:
                dependencies[str(block.uuid)] = map(str, block.get_input_blocks())

        return dependencies

    def get_meta_block_by_sub_scope(self, scope_name, redis_instance=None):
        if redis_instance is None:
            r = get_redis_instance()
        else:
            r = redis_instance

        block_uuid = r.hget(ExpKeys.get_scope_creating_block_uuid_keys(self.pk), scope_name)
        if not block_uuid:
            raise KeyError("Doesn't have a scope with name %s" % scope_name)
        else:
            return self.get_block(block_uuid, r)


    # def get_registered_variables(self, redis_instance=None):
    #     """
    #     @type  redis_instance: Redis
    #     @param redis_instance: Redis
    #
    #     @return: All register to experiment variables
    #     @rtype: list # of  [scope, uuid, var_name, var_data_type]
    #     """
    #
    #     if redis_instance is None:
    #         r = get_redis_instance()
    #     else:
    #         r = redis_instance
    #
    #     variables = []
    #     for key, val in r.hgetall(ExpKeys.get_scope_vars_keys(self.pk)).iteritems():
    #         #scope, uuid, var_name, var_data_type = pickle.loads(val)
    #         variables.append(pickle.loads(val))
    #
    #     return variables
    #
    # def get_visible_variables(self, scopes=None, data_types=None, redis_instance=None):
    #     if scopes is None:
    #         scopes = ["root"]
    #
    #     scopes = set(scopes)
    #     scopes.add("root")
    #
    #     if redis_instance is None:
    #         r = get_redis_instance()
    #     else:
    #         r = redis_instance
    #
    #     all_variables = r.hgetall(ExpKeys.get_scope_vars_keys(self.pk))
    #     visible = []
    #     for key, val in all_variables.iteritems():
    #         scope, uuid, var_name, var_data_type = pickle.loads(val)
    #         if scope not in scopes:
    #             continue
    #
    #         if data_types is None or var_data_type in data_types:
    #             visible.append((uuid, var_name))
    #
    #     return visible

    # def register_variable(self, scope, block_uuid, var_name, data_type, redis_instance=None):
    #     if redis_instance is None:
    #         r = get_redis_instance()
    #     else:
    #         r = redis_instance
    #
    #     record = pickle.dumps((scope, block_uuid, var_name, data_type))
    #     r.hset(ExpKeys.get_scope_vars_keys(self.pk), "%s:%s" % (block_uuid, var_name), record)


def delete_exp(exp):
    """
        We need to clean 3 areas:
            - keys in redis storage
            - uploaded and created files
            - delete exp object through ORM

        @param exp: Instance of Experiment  to be deleted
        @return: None

    """
    # redis
    r = get_redis_instance()
    all_exp_keys = ExpKeys.get_all_exp_keys_key(exp.pk)
    keys_to_delete = r.smembers(all_exp_keys)
    keys_to_delete.update(all_exp_keys)
    r.delete(keys_to_delete)

    # uploaded data
    data_files = UploadedData.objects.filter(exp=exp)
    for f in data_files:
        try:
            os.remove(f.data.path)
        except:
            pass
        f.delete()
    try:
        shutil.rmtree(exp.get_data_folder())
    except:
        pass

    # deleting an experiment
    exp.delete()

def content_file_name(instance, filename):
    return '/'.join(map(str, ['data', instance.exp.author.id, instance.exp.pk, filename]))


class UploadedData(models.Model):
    exp = models.ForeignKey(Experiment)
    var_name = models.CharField(max_length=255)
    filename = models.CharField(max_length=255, default="default")
    data = models.FileField(null=True, upload_to=content_file_name)

    def __unicode__(self):
        return u"%s:%s" % (self.exp.pk, self.var_name)


def gene_sets_file_name(instance, filename):
    return "broad_institute/%s" % filename


class BroadInstituteGeneSet(models.Model):
    section = models.CharField(max_length=255)
    name = models.CharField(max_length=255)
    UNIT_CHOICES = (
        ('entrez', 'Entrez IDs'),
        ('symbols', 'gene symbols'),
        ('orig', 'original identifiers'),
    )
    unit = models.CharField(max_length=31,
                            choices=UNIT_CHOICES,
                            default='entrez')
    gmt_file = models.FileField(null=False, upload_to=gene_sets_file_name)

    def __unicode__(self):
        return u"%s: %s. Units: %s" % (self.section, self.name, self.get_unit_display())

    def get_gene_sets(self):
        gene_sets = GeneSets(None, None)
        gene_sets.storage = GmtStorage(self.gmt_file.path)
        gene_sets.metadata["gene_units"] = self.unit
        return gene_sets

    @staticmethod
    def get_all_meta():
        res = []
        raw = BroadInstituteGeneSet.objects.order_by("section", "name", "unit").all()
        for record in raw:
            res.append({
                "pk": record.pk,
                "section": record.section,
                "name": record.name,
                "unit": record.unit,
                "str": str(record),
            })
        return res
