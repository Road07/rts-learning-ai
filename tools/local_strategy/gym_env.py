"""Gymnasium single-player control over the real fixed-step OpenBFME simulator.

No policy is loaded/trained/activated. Other players use native AI. Observation
and candidates come from the existing fog-filtered entity/mechanics interface.
"""
import copy
import math
import json
from dataclasses import asdict
from pathlib import Path
import sys
import numpy as np
import gymnasium as gym
from gymnasium import spaces
from gymnasium.error import InvalidAction,ResetNeeded
from gym_bridge import NativeMatchBackend
from gym_reward import PotentialConfig,PotentialReward,SCHEMA as REWARD_SCHEMA
from run_match import HERE,ROOT,FACTIONS,read,sha
sys.path.insert(0,str(HERE/'training'));sys.path.insert(0,str(HERE/'service'))
from public_game_rules import PublicGameRules
from spend_policy import legal_spend_options
from entity_codec import EntityCodec,ENTITY_WIDTH,ACTION_WIDTH,GLOBAL_WIDTH,KINDS

DEFAULT_FACTIONS=('FactionDwarves','FactionWild','FactionDwarves','FactionElves','FactionIsengard','FactionMordor')

class OpenBFMEEnv(gym.Env):
    metadata={'render_modes':[]}

    def __init__(self,*,factions=DEFAULT_FACTIONS,agent_index=0,map_name='maps/map wor lostriand/map wor lostriand.map',
                 duration=180.,time_scale=10.,max_entities=256,workspace_root=None,engine_package=None,
                 rules_config=None,timeout=120.,episode_timeout=3600.,bfme2='D:/Games/BFME2',rotwk='D:/Games/RotWK',
                 a=1e-4,b=.01,c=1e-4,gamma=.99,
                 native_difficulty='brutal',positions=None,runtime_cache=None,persistent_games=False,
                 render_mode=None,_backend_factory=NativeMatchBackend,_rules=None):
        if render_mode is not None:raise ValueError('This adapter is headless; render_mode must be None')
        if len(factions) not in (2,6) or any(f not in FACTIONS for f in factions):raise ValueError('Supply two or six installed factions')
        if type(agent_index) is not int or not 0<=agent_index<len(factions):raise ValueError('Invalid agent slot')
        if native_difficulty not in ('easy','medium','hard','brutal'):raise ValueError('Invalid native difficulty')
        if positions is not None and (len(positions)!=len(factions) or len(set(positions))!=len(positions) or any(type(p) is not int or not 0<=p<8 for p in positions)):raise ValueError('Invalid start positions')
        if not math.isfinite(duration) or not .2<=duration<=86400 or not math.isclose(duration*5,round(duration*5),abs_tol=1e-8):raise ValueError('Duration must be a positive multiple of 0.2 seconds')
        if not math.isfinite(time_scale) or not .01<=time_scale<=1000 or any(not math.isfinite(v) or v<=0 for v in (timeout,episode_timeout)):raise ValueError('Invalid speed/timeout')
        self.render_mode=None;self._factory=_backend_factory;self._backend=None;self._needs_reset=True
        self._persistent_games=persistent_games
        if persistent_games:
            if _backend_factory is not NativeMatchBackend:raise ValueError('Persistent games require native session backend')
            from gym_session import SessionMatchBackend
            self._factory=SessionMatchBackend
        self.reward_config=PotentialConfig(a,b,c,gamma);self._reward_log=None
        if _rules is None:
            config_path=Path(rules_config or ROOT/'AI-Yeni-Model/ai-service/runtime.json').resolve()
            config=read(config_path);rules_path=Path(config['game_rules'])
            if not rules_path.is_absolute():rules_path=config_path.parent/rules_path
            if sha(rules_path)!=config['game_rules_sha256']:raise ValueError('Pinned public rules changed')
            _rules=PublicGameRules(rules_path)
        self.rules=_rules;self.codec=EntityCodec(self.rules,max_entities);self.cap=self.codec.max_entities
        self._settings=dict(factions=factions,agent_index=agent_index,map_name=map_name,duration=duration,time_scale=time_scale,
            workspace_root=workspace_root or ROOT/'AI-Test-Sahasi/gym-runs',engine_package=engine_package,
            timeout=timeout,episode_timeout=episode_timeout,bfme2=bfme2,rotwk=rotwk,
            native_difficulty=native_difficulty,positions=positions)
        if runtime_cache is not None:self._settings['runtime_cache']=runtime_cache
        self.action_space=spaces.MultiDiscrete([64,65])
        vocab=len(self.codec.vocabulary);cap=self.cap
        def head(count):
            return spaces.Dict({'features':spaces.Box(0.,3.,(count,ACTION_WIDTH),np.float32),
                'kinds':spaces.MultiDiscrete(np.full(count,len(KINDS))),
                'templates':spaces.MultiDiscrete(np.full(count,vocab)),
                'actors':spaces.MultiBinary((count,cap)),'targets':spaces.MultiBinary((count,cap)),
                'legal':spaces.MultiBinary(count)})
        self.observation_space=spaces.Dict({'entities':spaces.Box(0.,3.,(cap,ENTITY_WIDTH),np.float32),
            'entity_valid':spaces.MultiBinary(cap),'entity_templates':spaces.MultiDiscrete(np.full(cap,vocab)),
            'relations':spaces.MultiDiscrete(np.full(cap,4)),'owner_factions':spaces.MultiDiscrete(np.full(cap,8)),
            'roles':spaces.MultiDiscrete(np.full(cap,9)),'faction':spaces.Discrete(7),
            'globals':spaces.Box(0.,3.,(GLOBAL_WIDTH,),np.float32),
            'heads':spaces.Dict({'tactical':head(64),'spend':head(65)})})

    def _encode(self,packet,initial=False):
        raw=copy.deepcopy(packet['snapshot']);obs=raw['observation'];frame=int(obs['decision_frame'])
        if not obs.get('model_only') or obs['faction']!=self._settings['factions'][self._settings['agent_index']]:raise ValueError('Unexpected controlled player')
        if initial:self._first_frame=frame;self._frame=frame;self._player=obs['player_index']
        if obs['player_index']!=self._player or (not initial and frame<=self._frame):raise ValueError('Discontinuous native observation')
        delta=0. if initial else (frame-self._frame)/5.;self._frame=frame
        tactical=raw['candidates'];spend=legal_spend_options(raw.get('production_options',[]),float(obs.get('money',0)))
        if not 1<=len(tactical)<=64 or len(spend)>65:raise ValueError('Native choice count exceeds fixed observation spaces')
        self.rules.attach(obs,tactical,spend)
        self._choices={'tactical':tactical,'spend':spend}
        encoded=self.codec.encode(obs,self._choices,delta)
        result={}
        for key in ('entities','entity_valid','entity_templates','relations','owner_factions','roles'):
            value=encoded[key];shape=(self.cap,)+value.shape[1:]
            array=np.zeros(shape,dtype=np.int8 if value.dtype==bool else value.dtype);array[:value.shape[0]]=value;result[key]=array
        result.update(faction=encoded['faction'],globals=encoded['globals'],heads={})
        for name,count in (('tactical',64),('spend',65)):
            result['heads'][name]={}
            for key,value in encoded['heads'][name].items():
                if key=='ids':continue
                shape=(count,self.cap) if key in ('actors','targets') else (count,)+value.shape[1:]
                array=np.zeros(shape,dtype=np.int8 if value.dtype==bool else value.dtype)
                if value.ndim==2 and key in ('actors','targets'):array[:value.shape[0],:value.shape[1]]=value
                else:array[:value.shape[0]]=value
                result['heads'][name][key]=array
        # Only the controlled player's fog-filtered snapshot is exposed. The full
        # offline scoreboard (including opponents) remains in the result file.
        public_obs=copy.deepcopy(obs)
        for key in ('match_id','diagnostic_session'):public_obs.pop(key,None)
        info={'frame':frame,'player':self._player,'elapsed_seconds':(frame-self._first_frame)/5.,'step_seconds':delta,
              'dropped_entities':encoded['dropped_entities'],'action_ids':{k:[c['id'] for c in v] for k,v in self._choices.items()},
              'policy_observation':public_obs,'reward_scheme':REWARD_SCHEMA}
        if not self.observation_space.contains(result):raise ValueError('Encoded observation is outside declared Gym spaces')
        return result,info

    def reset(self,*,seed=None,options=None):
        if options:raise ValueError('Set match configuration in the environment constructor')
        if seed is not None and (not isinstance(seed,(int,np.integer)) or not 0<=int(seed)<=2147483647):raise ValueError('Native seed must be 0..2147483647')
        super().reset(seed=None if seed is None else int(seed))
        if self._persistent_games and self._backend is not None:
            self._needs_reset=True
            if self._reward_log is not None:self._reward_log.close();self._reward_log=None
        else:self.close()
        native_seed=int(seed) if seed is not None else int(self.np_random.integers(0,2147483648))
        if self._backend is None:self._backend=self._factory(**self._settings)
        if self._settings['engine_package'] is None and hasattr(self._backend,'settings'):
            self._settings['engine_package']=self._backend.settings['engine_package']
        try:
            packet=self._backend.reset(native_seed)
            if packet['done']:raise RuntimeError('Match ended before the first agent decision')
            observation,info=self._encode(packet,initial=True);info['seed']=native_seed
            self._reward=PotentialReward(self.reward_config)
            initial=self._reward.reset(packet['snapshot'].get('reward_state'),self._player,self._frame)
            self._reward_total=0.;self._reward_steps=0
            if hasattr(self._backend,'directory'):
                self._reward_log=(Path(self._backend.directory)/'reward.jsonl').open('x',encoding='utf-8')
            self._log_reward({'event':'reset','seed':native_seed,'frame':self._frame,'schema':REWARD_SCHEMA,
                'config':asdict(self.reward_config),'opponent_aggregation':'hostile_player_mean',
                'potential':initial,'privileged_reward_state':packet['snapshot']['reward_state']})
        except BaseException:self.close();raise
        self._needs_reset=False;return observation,info

    def step(self,action):
        if self._needs_reset:raise ResetNeeded('Call reset() before stepping a new episode')
        if not self.action_space.contains(action):raise InvalidAction('Expected [tactical_index, spend_index]')
        a,b=map(int,action)
        if a>=len(self._choices['tactical']) or b>=len(self._choices['spend']):raise InvalidAction('Padded action is masked; no command was sent')
        answer={'candidate_id':self._choices['tactical'][a]['id'],'production_id':self._choices['spend'][b]['id']}
        try:
            packet=self._backend.step(answer);observation,info=self._encode(packet)
        except BaseException:self.close();raise
        terminated=False;truncated=False;reward=0.
        if packet['done']:
            status=packet['snapshot'];won=bool(status.get('won'));lost=bool(status.get('defeated'))
            if won and lost:raise RuntimeError('Conflicting native terminal state')
            terminated=won or lost
            truncated=not terminated and packet['reason']=='duration'
            if not terminated and not truncated:raise RuntimeError('Native match ended without a classified agent outcome')
            reward=1. if won else -1. if lost else 0.
            info['end_reason']=packet['reason'];self._needs_reset=True
        try:
            components,details=self._reward.step(packet['snapshot'].get('reward_state'),self._player,self._frame,reward,terminated,truncated)
            reward=components['total'];info['reward_components']=dict(components)
            self._reward_total+=reward;self._reward_steps+=1
            self._log_reward({'event':'step','frame':self._frame,'step':self._reward_steps,'components':components,
                **details,'terminated':terminated,'truncated':truncated,'episode_total':self._reward_total,
                'privileged_reward_state':packet['snapshot']['reward_state']})
        except BaseException:self.close();raise
        return observation,reward,terminated,truncated,info

    def _log_reward(self,row):
        if self._reward_log is not None:
            self._reward_log.write(json.dumps(row,ensure_ascii=False,allow_nan=False)+'\n');self._reward_log.flush()

    def action_masks(self):
        if self._needs_reset:raise ResetNeeded('Call reset() before requesting masks')
        return np.concatenate([(np.arange(count)<len(self._choices[name])) for name,count in (('tactical',64),('spend',65))])

    def sample_action(self):
        if self._needs_reset:raise ResetNeeded('Call reset() before sampling')
        return np.asarray([self.np_random.integers(len(self._choices[h])) for h in ('tactical','spend')],dtype=np.int64)

    def close(self):
        self._needs_reset=True
        if self._reward_log is not None:self._reward_log.close();self._reward_log=None
        if self._backend is not None:self._backend.close();self._backend=None

if 'OpenBFME-v0' not in gym.registry:
    gym.register('OpenBFME-v0',entry_point='gym_env:OpenBFMEEnv')
