import random
import math
import redis
import json
from config import app
from . import auth

#{'feed_engine':{'m0':0.345, 'm1':0.655}}
gamma=random.choice([0.1, 0.3, 0.5, 0,7, 0,9])
r = redis.StrictRedis(decode_responses=True)

def categorical_draw(probs):
  z = random.random()
  cum_prob = 0.0
  for i in range(len(probs)):
    prob = probs[i]
    cum_prob += prob
    if cum_prob > z:
      return i

  return len(probs) - 1


def get_sorted_weight(campaign):
  values=r.hgetall(campaign)
  arm_dict=sorted(values.items())
  __key_for_debug=[arm[0] for arm in arm_dict if arm[0] is not None]
  debug_matrix("__key_for_debug", __key_for_debug, 11)
  debug_matrix("arm_dict", arm_dict, 11)
  return [float(arm[1]) for arm in arm_dict if arm[1] is not None] 

def get_redis_arm(campaign,arm_id):
  values=r.hgetall(campaign)
  array=[each for each in list(values.keys())]
  if len(array) > 0:
    return array[arm_id]
  else:
  	return None

def set_redis_value_float(campaign, arm, value):
  r.hset(campaign,arm,value)

def select_arm(campaign):
  weights = get_sorted_weight(campaign)
  debug_matrix("weights", weights, 11)
  n_arms = len(weights)
  total_weight = sum(weights)
  probs = [0.0 for i in range(n_arms)]
  for arm in range(n_arms):
    probs[arm] = (1 - gamma) * (weights[arm] / total_weight)
    probs[arm] = probs[arm] + (gamma) * (1.0 / float(n_arms))
  arm_id=categorical_draw(probs)
  debug_matrix("selected arm", arm_id, 11)
  return [arm_id,get_redis_arm(campaign,arm_id)]

def update(campaign, selected_arm_id, reward):
  weights = get_sorted_weight(campaign)
  n_arms = len(weights)
  total_weight = sum(weights)
  probs = [0.0 for i in range(n_arms)]
  for arm in range(n_arms):
    probs[arm] = (1 - gamma) * (weights[arm] / total_weight)
    probs[arm] = probs[arm] + (gamma) * (1.0 / float(n_arms))
  if (reward > 0):
    x = reward / probs[selected_arm_id]
    growth_factor = math.exp((gamma / n_arms) * x)
    weights[selected_arm_id] = weights[selected_arm_id] * growth_factor
  else:
    weights[selected_arm_id]=weights[selected_arm_id]+reward #if there are more than 2 arms
  
  arm=get_redis_arm(campaign, selected_arm_id)
  set_redis_value_float(campaign, arm, weights[selected_arm_id])
#a debug matrix to highlight what i'm looking for
def debug_matrix(d_type, d_para, d_size):
  for __e in range (d_size,0,-1):
    print((11-__e) * ' ' + __e * '*')
  print ('')
  print ("%s parameter is: %s" %(d_type, d_para))
  for __g in range (d_size,0,-1):
    print(__g * ' ' + (11-__g) * '*')

@app.get("/api/<slug>/redis_result.json")
#@auth.require_user_admin
def redis_result(slug=None):
  return {'compaign': slug, 'result':r.hgetall(slug) or ''}
