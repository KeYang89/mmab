#---------------------update-------------------------
#in the future we can import an array from the rec_engine folder if we have multiple engines
#since we only have two engines, a static array ARMS in util is sufficient
#---------------------debug--------------------------
#for local testing, if you get WRONGTYPE errors
#run redis-cli and then flushall to ensure all cache is cleared
#currently it's not user specifc for each open
#---------------------logic--------------------------
#higher the reward, higher the chance to get selected
#when an arm is selected, reduce the reward a bit so we do not always choose the same arm
#adjusted_reward = open/(appear+1) + *bounus_of_an_arm - *reward/(position_sum+1.0)
#bonus_of_an_arm=math.sqrt(2*math.log(sum_arm('appear')))/float(appear_of_that_arm+1.0)
#ultimate goal is to get higher reward for the correct arm
#---------------------style--------------------------
#all external function will connect via engine_id
#all internal function will connect via arm
#---------------------ucb2---------------------------
#please do not delete the commented functions
#all commented functions can be used for plotting

import redis
from util import ARMS
import random
import math
import re


#remove these module if you'd like to turn off the json display
import json
from config import app

r = redis.StrictRedis(decode_responses=True)
#------parameters and random constant setting---------
#set TESTING to False if you'd like to stop hmab
TESTING = True 
#set alpha for tau and bonus so we don't overly exploit one arm
#after testing we can pick a more specific alpha
ALPHA = random.choice([0.1, 0.3, 0.5, 0,7, 0,9])

def get_tau(appear):
  return int(math.ceil((1 + ALPHA) ** appear))

def ind_max(x):
  m = max(x)
  return x.index(m)
#------------------data prepration------------------
#all redis data, including None, array will be set to hash/string by default
#all calculation related parameter will be set to float
#all state related parameter will be set to int
#all output array will be cleaned as string or numeric accordingly
#arm info
def set_redis_arm_info(arm, req_type, value):
  r.hset(arm,req_type,value)

#validation or init
def get_redis_arm_info(arm, req_type):
  if r.hget(arm,req_type):
    return float(r.hget(arm,req_type))
  else:
    set_redis_arm_info(arm,req_type,0.0)
    return 0.0
#state info
def set_redis_state_info(state,value):
  r.hset('state_dict', state, value)

def get_redis_state_info(state):
  if r.hget('state_dict',state):
    return int(r.hget('state_dict',state))
  else:
    set_redis_state_info(state, 0)
    return 0

def get_array_str_from_redis(arm, req_type):
  array_dir=r.hget(arm, req_type)
  array_str=''
  if array_dir!='None' and (array_dir is not None):
    array_str=array_dir[1:-1].replace(' ','')
  return array_str

def clean_array_str(array_str):
  #use re, do not use isdigit
  array_str=[re.sub(r'[^\d.]+', '', s) for s in array_str.split(',')]
  array_str=[i for i in array_str if i !='' and i !='None']
  return array_str

def str_to_array(array_str):
  if len(array_str) > 0:
    array=[float(i) for i in array_str]
  else:
    array=[]
  return array

def set_exchange_post_ids(engine_id, ex_feed_ids):
  arm=ARMS[engine_id]
  set_redis_arm_info(arm,'post_ids',ex_feed_ids)

#use merge_post_ids if we wanted to expand the diameter
def merge_post_ids(engine_id,new_array):
  arm=ARMS[engine_id]
  post_ids=list(set(get_array_str_from_redis(arm,'post_ids').split(','))+new_array)
  return post_ids

def in_exchange_feed_position(engine_id, post_id):
  arm=ARMS[engine_id]
  post_ids_str=get_array_str_from_redis(arm,'post_ids')
  #do not use hscan, unnecessary
  post_ids_array=post_ids_str.split(',')
  #debug_matrix('post_ids_array # in_exchange_feed_position', post_ids_array, 11)  
  if len(post_ids_str) > 5 and (str(post_id) in post_ids_str): 
    #'None' has length 4, and our posts id length 1 ~ 5, 
    # all post id together will definitely be larger than 5
    position=float(post_ids_array.index(str(post_id)))
    adjust_para(arm,'position_sum', position)
    return position
  else:
    return -1

def adjust_para(arm, req_type, para):
  if isinstance(para,float):
    r.hincrbyfloat(arm, req_type, para)
  else:
    print("sorry you can only pass float as para here, your para is ", str(para))

# #reward historical array for plotting
# def set_reward_array(arm, reward):
#   reward_array_str=get_array_str_from_redis(arm, 'reward_array')
#   reward_array=clean_array_str(reward_array_str)
#   #debug_matrix('reward_array - before append', reward_array, 11)
#   reward_array.append(str(reward))
#   #debug_matrix('reward_array - post append', reward_array, 11)
#   reward_array=str_to_array(reward_array)
#   set_redis_arm_info(arm,'reward_array',reward_array)
#   set_redis_arm_info(arm,'score',average_reward(reward_array))

def set_reward_bonus(arm, bonus):
  reward_ex=get_redis_arm_info(arm,'reward')
  reward=reward_ex+bonus
  set_redis_arm_info(arm,reward,'reward')

#------------------------calculation----------------------
# def average_reward(reward_array):
#   if len(reward_array)>0:
#     return sum(reward_array)/len(reward_array)
#   else:
#     return "Insufficent data"

def get_bonus(arm):
  appear=get_redis_arm_info(arm,'appear')
  total_appear=sum_arm('appear')
  #more appear, less bonus
  #after each selection, slowly reduce its bonus so we do not always choose it
  #ucb1--------------------------ucb1
  #use ucb1 if you only need hmab run for a short period of time : < 500 impressions 
  #bonus=math.sqrt(2*math.log(total_appear))/(appear+1.0)
  #ucb2--------------------------ucb2
  #use ucb2 for long term testing : > 500 impressions
  tau = get_tau(appear)
  #debug_matrix('tau', tau, 11)
  position_sum=get_redis_arm_info(arm,'position_sum')
  position_adjust=math.log(position_sum*appear + math.e) #prevent math.log(0)
  bonus = math.sqrt((1.0 + ALPHA) * math.log(math.e * (appear+1.0)/ tau) / (2 * tau * position_adjust))
  debug_matrix('get_bonus', bonus, 11)
  set_redis_arm_info(arm,'bonus', bonus) 
  return bonus

#calculate sum of appear etc of all arms
def sum_arm(req_type):
  total=0.0
  for arm in ARMS:
    __s_arm= get_redis_arm_info(arm,req_type)
    if __s_arm:
      total=total+__s_arm
  return total

#update reward for each appear or open, increment them by 1.0 each time, compute the ratio
#consider position_sum
def update_reward(engine_id, req_type):
  arm=ARMS[engine_id]
  adjust_para(arm,req_type,1.0)
  appear=get_redis_arm_info(arm,'appear')
  open_updated=get_redis_arm_info(arm,'open')
  bonus=get_bonus(arm)
  
  #get previous reward
  reward=get_redis_arm_info(arm, 'reward')
  #reward baseline
  if appear and open_updated and bonus: 
    reward=open_updated/(appear+1.0) + bonus #prevent 0 division
  #reward bonus
  #adjuted_reward first consider the postion_sum
  #larger the position_sum, smaller the bonus
  set_redis_arm_info(arm,'reward',reward) #update reward
  #debug_matrix('reward', reward, 11)
  #debug--------------------------debug
  #set_reward_array(arm,reward)

#set each arm to at least play tau(appear+1)-tau(appear) episodes
#increment appear by 1.0
def set_arm(arm):
  #set current_arm id in redis
  engine_id=ARMS.index(arm)
  set_redis_state_info('current_arm_id',engine_id)
  #compute episodes
  next_update = get_redis_state_info('next_update')
  appear=get_redis_arm_info(arm, 'appear')
  next_update += max(1, get_tau(appear + 1) - get_tau(appear))
  set_redis_state_info('next_update',int(next_update))
  #increment appear by 1.0 and update reward
  update_reward(engine_id,'appear')

#when the score of the arms are too close
def rand_draw(probs):
  z = random.random()
  cum_prob = 0.0
  for i in range(len(probs)):
    prob = probs[i]
    cum_prob += prob
    if cum_prob > z:
      return i
  return len(probs) - 1

#shuffle the choice
def shuffle():
  if TESTING==False:
    return None

  appear_total=sum_arm('appear')
  reward_total=sum_arm('reward')
  # score_total=sum_arm('score')
  #do not use array history
  score_total=reward_total
  set_redis_state_info('current_round',int(appear_total))
  #initial state, make sure we played each arm once
  for arm in ARMS:
    if get_redis_arm_info(arm, 'appear') is None or get_redis_arm_info(arm, 'appear') == 0.0:
      set_arm(arm)
      return ARMS.index(arm)

  #if any of the arm <= 0.101 score or less than (ALPHA+1)*10 count, it is highly possible that it's under explored
  for arm in ARMS:
    if get_redis_arm_info(arm, 'score')<=0.101 or get_redis_arm_info(arm, 'appear') < (ALPHA+1)*10:
      set_arm(arm)
      return ARMS.index(arm)
  
  #make sure we are not still playing the previous arm.
  #debug_matrix('sum_appear', sum_arm('appear'), 11)
  if get_redis_state_info('next_update') and get_redis_state_info('next_update') > appear_total:
    selected_engine_id=get_redis_state_info('current_arm_id')
    selected_arm=ARMS[selected_engine_id]
    update_reward(selected_engine_id,'appear')
    return selected_engine_id

  #after initial state, we use ucb2    
  chance_bucket=[]
  #use reward average/score to replace reward and be less aggressive
  for arm in ARMS:
  	#reward_avg=get_redis_arm_info(arm,'score')
    #reset when reward goes down to 0 or below
    if reward_total<=0.0:
  	  reward_total=0.1
  	  #prevent 0 division
    #chance=reward_avg/reward_total
    chance=reward/reward_total
    chance_bucket.append(chance)
  #get selected_engine_id and update the select_count

  #if arms have very close score (0.01) - consider not significant, we toss a dice
  if len(chance_bucket)>0 and max(chance_bucket)-min(chance_bucket) < 0.01:
    debug_matrix('chance_bucket', chance_bucket, 11)
    selected_engine_id=rand_draw(chance_bucket)
  else:
    #otherwise, we choose the best arm
    selected_engine_id=int(ind_max(chance_bucket))
  
  selected_arm=ARMS[selected_engine_id]
  set_arm(selected_arm)
  #debug_matrix('engine', selected_engine_id, 11)
  return selected_engine_id

#a debug matrix to highlight what i'm looking for
def debug_matrix(d_type, d_para, d_size):
  for __e in range (d_size,0,-1):
    print((11-__e) * ' ' + __e * '*')
  print ('')
  print ("%s parameter is: %s" %(d_type, d_para))
  for __g in range (d_size,0,-1):
    print(__g * ' ' + (11-__g) * '*')

@app.get("/api/redis_result.json")
def redis_result():
  return {#'score': [get_redis_arm_info(arm,'score') for arm in ARMS],
          'score': [get_redis_arm_info(arm,'reward') for arm in ARMS],
          'time_stamp': [r.hget(arm,'time_stamp') for arm in ARMS],
          'steps':get_redis_state_info('current_round'),
          'alpha':ALPHA
          }
