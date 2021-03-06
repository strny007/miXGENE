import csv
import json
from collections import defaultdict
import logging

import numpy as np

from django.http import HttpResponse, HttpResponseNotAllowed, HttpRequest, HttpResponseBadRequest
from django.template import RequestContext, loader
from django.shortcuts import redirect

from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect, csrf_exempt

from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required

from webapp.models import Experiment, UploadedData, delete_exp, Article, ExperimentLog, HelpBlock, HelpBlockAttribute
from webapp.forms import UploadForm
from webapp.scope import Scope
from webapp.store import add_block_to_exp_from_dict
from workflow.blocks import blocks_by_group

from mixgene.util import dyn_import, get_redis_instance, mkdir, log_timing

log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)

def index(request):
    template = loader.get_template('index.html')
    context = RequestContext(request, {
        "next": "/",
    })
    return HttpResponse(template.render(context))


def about(request):
    template = loader.get_template('about.html')
    context = RequestContext(request, {
        "next": "/",
    })
    return HttpResponse(template.render(context))


def contact(request):
    template = loader.get_template('contact.html')
    context = RequestContext(request, {
        "next": "/",
    })
    return HttpResponse(template.render(context))


def articles(request, article_type=None):
    log.info("Article type: %s", article_type)
    if article_type not in ["cs", "t"]:
        article_type = "cs"
    template = loader.get_template('articles/list.html')
    context = RequestContext(request, {
        "next": "/",
        "articles": Article.objects.filter(article_type=article_type),
        "articles_page_active": True,
        "article_type": article_type,
        "article_type_title": dict(Article.type_choice)[article_type],
    })
    return HttpResponse(template.render(context))


def article(request, article_id):
    template = loader.get_template('articles/page.html')
    context = RequestContext(request, {
        "next": "/",
        "article": Article.objects.get(pk=int(article_id)),
        "articles_page_active": True,
    })
    return HttpResponse(template.render(context))

def run_detail(request, exp_id):
    exp = Experiment.objects.get(pk=exp_id)

    context = {
        "next": "/",
        "scope": "root",
        "exp": exp,
        "exp_json": json.dumps({
            "exp_id": exp_id,
        }),
        "ro_mode": "true"
    }
    template = loader.get_template('constructor.html')
    context = RequestContext(request, context)
    return HttpResponse(template.render(context))


def constructor(request, exp_id):
    exp = Experiment.objects.get(pk=exp_id)

    context = {
        "next": "/",
        "scope": "root",
        "exp": exp,
        "exp_json": json.dumps({
            "exp_id": exp_id,
        }),
    }

    template = loader.get_template('constructor.html')
    context = RequestContext(request, context)
    return HttpResponse(template.render(context))


def exp_ro(request, exp_id):
    exp = Experiment.objects.get(pk=exp_id)

    context = {
        "next": "/",
        "scope": "root",
        "exp": exp,
        "exp_json": json.dumps({
            "exp_id": exp_id,
        }),
        "ro_mode": "true"
    }
    template = loader.get_template('constructor.html')
    context = RequestContext(request, context)
    return HttpResponse(template.render(context))

def exp_log(request, exp_id):
    import hashlib
    exp_logs = ExperimentLog.objects.filter(experiment_id=exp_id).order_by('-id')
    resp = HttpResponse(content_type="application/json")
    columns = ["timestamp", "block", "severity", "message"]
    table_headers = ["#"] + columns
    column_title_to_code_name = {
        title: "_" + hashlib.md5(title).hexdigest()[:8]
        for title in table_headers
    }
    fields_list = [column_title_to_code_name[title] for title in table_headers]

    from django.conf import settings
    from pytz import timezone

    settings_time_zone = timezone(settings.TIME_ZONE)

    fmt = '%Y-%m-%d %H:%M:%S %Z'
    result = {
        "columns": [
            {
                "title": title,
                "field": column_title_to_code_name[title],
                "visible": True
            }
            for title in table_headers
        ],
        "rows": [
            dict(zip(fields_list, map(str, [e_log.id, e_log.created.astimezone(settings_time_zone).strftime(fmt), e_log.block_uuid, e_log.severity, e_log.message])))
            for e_log in exp_logs
        ]
    }
    json.dump(result, resp)
    return resp

def exp_sub_resource(request, exp_id, sub):
    exp = Experiment.objects.get(pk=exp_id)
    attr = getattr(exp, str(sub))
    if callable(attr):
        result = {'data': attr()}
    else:
        result = {'data': attr}

    resp = HttpResponse(content_type="application/json")
    json.dump(result, resp)
    return resp


@log_timing
def exp_change_name(request, exp_id):
    exp = Experiment.objects.get(pk=exp_id)
    exp.name = request.GET["exp_name"]
    exp.save()
    resp = HttpResponse(content_type="application/json")
    json.dump({'ok': 'ok'}, resp)
    return resp

@csrf_protect
@log_timing
def blocks_resource(request, exp_id):
    allowed = ["GET", "POST"]
    if request.method not in allowed:
        return HttpResponseNotAllowed(["GET", "POST"])

    exp = Experiment.objects.get(pk=exp_id)
    r = get_redis_instance()

    new_block = None
    if request.method == "POST":
        try:
            received_block = json.loads(request.body)
        except Exception, e:
            return HttpResponseBadRequest()
        new_block = add_block_to_exp_from_dict(exp, received_block)

    # TODO: Move to model logic
    blocks_uuids = exp.get_all_block_uuids(redis_instance=r)
    blocks = exp.get_blocks(blocks_uuids, redis_instance=r)

    blocks_by_bscope = defaultdict(list)
    for uuid, block in blocks:
        blocks_by_bscope[block.scope_name].append(uuid)

    aliases_map = exp.get_block_aliases_map(redis_instance=r)

    variables = []
    for scope_name, _ in exp.get_all_scopes_with_block_uuids(redis_instance=r).iteritems():
        scope = Scope(exp, scope_name)
        scope.load(redis_instance=r)
        scope.update_scope_vars_by_block_aliases(aliases_map)

        variables.extend(scope.scope_vars)

    result = {
        "blocks_uuids": blocks_uuids,

        "blocks_by_bscope": blocks_by_bscope,
        "blocks_by_group": blocks_by_group,

        "vars": [var.to_dict() for var in variables],
        "vars_by_key": {var.pk: var.to_dict() for var in variables},

        "new_block_uuid": new_block.uuid if new_block else "",
    }

    resp = HttpResponse(content_type="application/json")
    json.dump(result, resp)
    return resp

import json
class SetEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, set):
            return list(obj)
        return json.JSONEncoder.default(self, obj)

@csrf_protect
@log_timing
def block_resource(request, exp_id, block_uuid, action_code=None):
    """

    @type request: HttpRequest
    """
    exp = Experiment.objects.get(pk=exp_id)
    # import ipdb; ipdb.set_trace()
    block = exp.get_block(str(block_uuid))

    # import time; time.sleep( 0.05)
    action_result = None

    if request.method == "DELETE":
        exp.remove_block(block)
        return HttpResponse(status=204)

    if request.method == "POST":
        try:
            received_block = json.loads(request.body)
        except Exception, e:
            # TODO log errors
            received_block = {}
        action_result = block.apply_action_from_js(action_code, exp=exp, request=request, received_block=received_block)

    if request.method in ["GET", "POST"]:
        # TODO: split into two views
        resp = HttpResponse(content_type="application/json")
        if action_result is None:
            block_dict = exp.get_block(block_uuid).to_dict()
            json.dump(block_dict, resp, cls=SetEncoder)
        else:
            json.dump(action_result, resp, cls=SetEncoder)
        return resp

    return HttpResponseNotAllowed(["POST", "GET", "DELETE"])


#@csrf_protect
def block_field_resource(request, exp_id, block_uuid, field, format=None):
    format = format or "json"
    exp = Experiment.objects.get(pk=exp_id)
    # import ipdb; ipdb.set_trace()
    block = exp.get_block(str(block_uuid))
    attr = getattr(block, field)
    if callable(attr):
        data = attr(exp, request)
    else:
        data = attr

    if format == "json":
        content_type = "application/json"
        resp = HttpResponse(content_type=content_type)
        resp['Content-Disposition'] = 'attachment; filename=export.json'
        json.dump(data, resp, cls=SetEncoder)
    elif format == "csv":
        content_type = "text/csv"
        resp = HttpResponse(content_type=content_type)
        resp.write(data)

    return resp


def block_sub_page(request, exp_id, block_uuid, sub_page):
    exp = Experiment.objects.get(pk=exp_id)
    block = exp.get_block(block_uuid)

    template = loader.get_template(block.pages[sub_page]['widget'])
    context = {
        "block_": block,
        "exp": exp,
    }
    context = RequestContext(request, context)
    return HttpResponse(template.render(context))


def block_method(request, exp_id, block_uuid, method):
    if request.method == "POST":
        exp = Experiment.objects.get(pk=exp_id)
        block = exp.get_block(str(block_uuid))
        if not hasattr(block, method) :
            raise Exception("Block %s doesn't have method `%s`" % (block.base_name, method))
        else:
            bound_func = getattr(block, method)
            if not callable(bound_func):
                raise Exception("Block %s attribute `%s` isn't callable" % (block.base_name, method))
            else:
                res = bound_func(exp, request.body)
                content_type = "application/json"
                resp = HttpResponse(content_type=content_type)
                json.dump(res, resp)
                return resp

    return HttpResponseNotAllowed(["POST"])


@csrf_protect
@never_cache
def upload_data(request):
    if request.method == "POST":
        form = UploadForm(request.POST, request.FILES)
        if form.is_valid():
            exp_id = form.cleaned_data['exp_id']
            block_uuid = form.cleaned_data['block_uuid']
            field_name = form.cleaned_data['field_name']
            file_obj = form.cleaned_data['file']
            multiple = form.cleaned_data['multiple']

            log.debug("Multiple: %s", multiple)
            exp = Experiment.get_exp_by_id(exp_id)
            block = exp.get_block(block_uuid)
            block.save_file_input(
                exp, field_name, file_obj,
                multiple=multiple,
                upload_meta=request.POST["upload_meta"]
            )

    return HttpResponse(status=204)


@csrf_protect
@never_cache
def create_user(request):
    if 'username' not in request.POST:
        template = loader.get_template('auth/user_creation.html')
        context = RequestContext(request, {
            "next": "/",
        })
        return HttpResponse(template.render(context))

    else:
        username = request.POST['username']
        email = request.POST['email']
        password = request.POST['password1']
        password2 = request.POST['password2']

        # Add nice warning for UI
        if password != password2:
            log.debug("User entered unmatched passwords")
            #TODO: redirect to create user page with warning, keep user name, flush passwords
        else:
            #TODO: check whether we already have user with the same name or email
            #TODO: add (or not) email validation ? captcha?
            User.objects.create_user(username, email, password)
            user = authenticate(username=username, password=password)
            login(request, user)

        # add user created page, or auto
        return redirect("/")


@login_required(login_url='/auth/login/')
@never_cache
def workflows(request):
    template = loader.get_template('workflows.html')
    context = RequestContext(request, {
        "exps": Experiment.objects.filter(author=request.user, is_run=False),
        "next": "/workflows",
        "exp_page_active": True,
    })
    return HttpResponse(template.render(context))

@login_required(login_url='/auth/login/')
@never_cache
def runs(request):
    template = loader.get_template('runs.html')
    context = RequestContext(request, {
        "runs": Experiment.objects.filter(author=request.user, is_run=True),
        "next": "/runs",
        "runs_page_active": True,
    })
    return HttpResponse(template.render(context))


@login_required(login_url='/auth/login/')
@csrf_protect
@never_cache
def alter_exp(request, exp_id, action):
    exp = Experiment.objects.get(pk=exp_id)
    if exp.author != request.user:
        return redirect("/") # TODO: show alert about wrong experiment

    if action == "execute":
        exp.execute()
        return redirect(request.POST.get("next") or "/runs/%s" % exp.pk) # TODO use reverse

    if action == 'delete': # TODO: check that exp state allows deletion
        delete_exp(exp)

    if action == 'update':
        exp.validate(request)

    # if action == 'save_gse_classes':
    #     factors = json.loads(request.POST['factors'])
    #     exp.update_ctx({"gse_factors": factors})

    return redirect(request.POST.get("next") or "/constructor/%s" % exp.pk) # TODO use reverse


@login_required(login_url='/auth/login/')
def add_experiment(request):
    exp = Experiment.objects.create(
        author=request.user,
        status='initiated',  # TODO: until layout configuration will be implemented
    )

    # TODO: move all init stuff to the model
    exp.save()
    exp.post_init()

    mkdir(exp.get_data_folder())
    return redirect("/constructor/%s" % exp.pk) # TODO use reverse


@login_required(login_url='/auth/login/')
@csrf_protect
@never_cache
def duplicate_experiment(request, exp_id):
    exp = Experiment.objects.get(pk=exp_id)
    exp.duplicate()
    # exp.pk = None
    # exp.save()
    return redirect("/constructor/%s" % exp.pk) # TODO use reverse


@never_cache
def get_tooltip(request, exp_id, block_uuid):
    try:
        field_title = request.GET['field_title']
    except KeyError:
        field_title = None
    exp = Experiment.objects.get(pk=exp_id)
    block = exp.get_block(block_uuid)
    try:
        if field_title:
            hba = HelpBlockAttribute.objects.get(help_block__block_name__icontains = block.name, attribute_name__icontains = field_title)
            hba_json = {"description": hba.parameters_description}
        else:
            hba = HelpBlock.objects.get(block_name__icontains = block.name)
            hba_json = {"description": hba.block_description}
    except Exception:
        hba_json = {"description": "Not available"}
    content_type = "application/json"
    resp = HttpResponse(content_type=content_type)
    json.dump(hba_json, resp)
    return resp

