import os
import json
import random
import datetime
from plugins import *
from common.log import logger
from bridge.context import ContextType
from bridge.reply import Reply, ReplyType
from apscheduler.schedulers.background import BackgroundScheduler

@register(name="idiom_game", desc="看图猜成语小游戏", version="1.0", author="lanvent")
class IdiomGame(Plugin):
    def __init__(self):
        super().__init__()
        self.handlers[Event.ON_HANDLE_CONTEXT] = self.on_handle_context
        
        # 加载成语题库
        try:
            curdir = os.path.dirname(__file__)
            config_path = os.path.join(curdir, "questions.json")
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.questions = data.get("questions", [])
        except Exception as e:
            logger.warn(f"[IdiomGame] 加载题库失败: {e}")
            self.questions = []
            
        # 存储当前游戏状态
        self.current_games = {}  # session_id -> game_info
        
        # 加载积分数据
        self.scores_file = os.path.join(curdir, "scores.json")
        self.load_scores()
        
        # 是否是每日答题时间
        self.is_daily_game_time = False
        
        # 启动定时任务
        self.scheduler = BackgroundScheduler()
        self.scheduler.add_job(self.start_daily_game, 'cron', hour=18, minute=0)
        self.scheduler.add_job(self.end_daily_game, 'cron', hour=23, minute=59)
        self.scheduler.start()
        
        # 加载用户昵称数据
        self.usernames_file = os.path.join(curdir, "usernames.json")
        self.load_usernames()
        
    def start_daily_game(self):
        """开始每日答题时间"""
        self.is_daily_game_time = True
        logger.info("[IdiomGame] 每日答题开始")
        
    def end_daily_game(self):
        """结束每日答题时间"""
        self.is_daily_game_time = False
        logger.info("[IdiomGame] 每日答题结束")
        
    def load_scores(self):
        """加载积分数据"""
        try:
            if os.path.exists(self.scores_file):
                with open(self.scores_file, "r", encoding="utf-8") as f:
                    self.scores = json.load(f)
            else:
                self.scores = {}
        except Exception as e:
            logger.warn(f"[IdiomGame] 加载积分失败: {e}")
            self.scores = {}
            
    def save_scores(self):
        """保存积分数据"""
        try:
            with open(self.scores_file, "w", encoding="utf-8") as f:
                json.dump(self.scores, f, ensure_ascii=False, indent=4)
        except Exception as e:
            logger.warn(f"[IdiomGame] 保存积分失败: {e}")
            
    def add_score(self, session_id, points):
        """增加积分"""
        if not self.is_daily_game_time:
            return  # 非每日答题时间不计分
            
        if session_id not in self.scores:
            self.scores[session_id] = 0
        self.scores[session_id] += points
        self.save_scores()
        
    def get_score(self, session_id):
        """获取积分"""
        return self.scores.get(session_id, 0)

    def get_random_questions(self, count=3):
        """获取随机题目"""
        return random.sample(self.questions, count)
        
    def load_usernames(self):
        """加载用户昵称数据"""
        try:
            if os.path.exists(self.usernames_file):
                with open(self.usernames_file, "r", encoding="utf-8") as f:
                    self.usernames = json.load(f)
            else:
                self.usernames = {}
        except Exception as e:
            logger.warn(f"[IdiomGame] 加载用户昵称失败: {e}")
            self.usernames = {}
            
    def save_usernames(self):
        """保存用户昵称数据"""
        try:
            with open(self.usernames_file, "w", encoding="utf-8") as f:
                json.dump(self.usernames, f, ensure_ascii=False, indent=4)
        except Exception as e:
            logger.warn(f"[IdiomGame] 保存用户昵称失败: {e}")
            
    def update_username(self, session_id, username):
        """更新用户昵称"""
        if session_id not in self.usernames or self.usernames[session_id] != username:
            self.usernames[session_id] = username
            self.save_usernames()
            
    def get_username(self, session_id):
        """获取用户昵称"""
        return self.usernames.get(session_id, "未知用户")
        
    def get_top_players(self, limit=10):
        """获取积分排行榜"""
        # 按积分排序
        sorted_scores = sorted(self.scores.items(), key=lambda x: x[1], reverse=True)
        # 取前N名
        top_n = sorted_scores[:limit]
        return [(self.get_username(sid), score) for sid, score in top_n]
        
    def get_help_text(self, **kwargs):
        help_text = "看图猜成语游戏指令:\n"
        help_text += "1. #猜成语 - 开始新游戏(每轮3题)\n"
        help_text += "2. #答案 [成语] - 提交答案\n" 
        help_text += "3. #结束 - 结束当前游戏\n"
        help_text += "4. #跳过 - 跳过当前题目（-2分）\n"
        help_text += "5. #积分 - 查看当前积分\n"
        help_text += "6. #排行 - 查看积分排行榜\n"
        help_text += "\n游戏规则：\n"
        help_text += "- 每日下午6点开启答题\n"
        help_text += "- 每轮游戏3题\n"
        help_text += "- 答对一题：+3分（仅限每日答题时间）\n"
        help_text += "- 跳过题目：-2分（仅限每日答题时间）\n"
        help_text += "- 非每日答题时间可以练习，但不计分"
        return help_text

    def on_handle_context(self, e_context: EventContext):
        if e_context['context'].type != ContextType.TEXT:
            return
            
        content = e_context['context'].content.strip()
        session_id = e_context['context'].session_id
        
        # 更新用户昵称
        username = e_context['context'].kwargs.get('msg').get('actual_user_nickname', "未知用户")
        self.update_username(session_id, username)
        
        if content == "#排行":
            top_players = self.get_top_players()
            if not top_players:
                reply = Reply(ReplyType.TEXT, "暂无排行数据")
            else:
                rank_text = "🏆 积分排行榜 TOP10\n\n"
                for i, (name, score) in enumerate(top_players, 1):
                    if i == 1:
                        rank_text += f"🥇 第{i}名: {name} - {score}分\n"
                    elif i == 2:
                        rank_text += f"🥈 第{i}名: {name} - {score}分\n"
                    elif i == 3:
                        rank_text += f"🥉 第{i}名: {name} - {score}分\n"
                    else:
                        rank_text += f"第{i}名: {name} - {score}分\n"
                reply = Reply(ReplyType.TEXT, rank_text)
            e_context['reply'] = reply
            e_context.action = EventAction.BREAK_PASS
            return
            
        if content == "#积分":
            score = self.get_score(session_id)
            # 获取用户排名
            all_scores = sorted(self.scores.items(), key=lambda x: x[1], reverse=True)
            rank = next((i for i, (sid, _) in enumerate(all_scores, 1) if sid == session_id), 0)
            
            reply_text = f"您当前的积分是：{score}\n"
            if rank > 0:
                reply_text += f"当前排名：第{rank}名"
            else:
                reply_text += "暂无排名"
                
            reply = Reply(ReplyType.TEXT, reply_text)
            e_context['reply'] = reply
            e_context.action = EventAction.BREAK_PASS
            return
            
        if content == "#猜成语":
            # 开始新游戏
            if len(self.questions) < 3:
                reply = Reply(ReplyType.TEXT, "题库加载失败,无法开始游戏")
                e_context['reply'] = reply
                e_context.action = EventAction.BREAK_PASS
                return
                
            if session_id in self.current_games:
                reply = Reply(ReplyType.TEXT, "您已经在游戏中了,请先完成当前题目或输入 #结束 结束游戏")
                e_context['reply'] = reply
                e_context.action = EventAction.BREAK_PASS
                return
                
            # 获取3个随机题目
            round_questions = self.get_random_questions(3)
            self.current_games[session_id] = {
                "questions": round_questions,
                "current_index": 0,
                "score": 0
            }
            
            # 发送第一题
            question = round_questions[0]
            img_path = os.path.join(os.path.dirname(__file__), "images", question["image"])
            reply = Reply(ReplyType.IMAGE_PATH, img_path)
            
            # 显示是否在计分时间
            if self.is_daily_game_time:
                info_text = "第1题/共3题 (每日答题时间，答题将计分)"
            else:
                info_text = "第1题/共3题 (非答题时间，答题不计分)"
            info_reply = Reply(ReplyType.TEXT, info_text)
            
            e_context['reply'] = [reply, info_reply]
            e_context.action = EventAction.BREAK_PASS
            return
            
        if content.startswith("#答案 "):
            if session_id not in self.current_games:
                reply = Reply(ReplyType.TEXT, "当前没有进行中的游戏,请先使用 #猜成语 开始游戏")
                e_context['reply'] = reply
                e_context.action = EventAction.BREAK_PASS
                return
                
            game = self.current_games[session_id]
            current_question = game["questions"][game["current_index"]]
            answer = content[3:].strip()
            
            if answer == current_question["answer"]:
                self.add_score(session_id, 3)  # 答对加3分
                game["score"] += 3
                score = self.get_score(session_id)
                
                if game["current_index"] < 2:  # 还有下一题
                    game["current_index"] += 1
                    next_question = game["questions"][game["current_index"]]
                    
                    # 发送答对提示和下一题
                    correct_reply = Reply(ReplyType.TEXT, f"恭喜你答对了! 答案就是: {answer}\n+3分！当前积分：{score}")
                    img_path = os.path.join(os.path.dirname(__file__), "images", next_question["image"])
                    next_reply = Reply(ReplyType.IMAGE_PATH, img_path)
                    info_reply = Reply(ReplyType.TEXT, f"第{game['current_index']+1}题/共3题")
                    e_context['reply'] = [correct_reply, next_reply, info_reply]
                else:  # 最后一题答对，结束游戏
                    reply = Reply(ReplyType.TEXT, 
                        f"恭喜你答对了! 答案就是: {answer}\n"
                        f"+3分！当前积分：{score}\n"
                        f"\n本轮游戏结束！\n"
                        f"本轮得分：{game['score']}分")
                    del self.current_games[session_id]
                    e_context['reply'] = reply
            else:
                reply = Reply(ReplyType.TEXT, "答案不对,再想想~")
                e_context['reply'] = reply
            
            e_context.action = EventAction.BREAK_PASS
            return
            
        if content == "#结束":
            if session_id in self.current_games:
                game = self.current_games[session_id]
                current_question = game["questions"][game["current_index"]]
                reply = Reply(ReplyType.TEXT, 
                    f"游戏结束,当前题目答案是: {current_question['answer']}\n"
                    f"本轮得分：{game['score']}分")
                del self.current_games[session_id]
                e_context['reply'] = reply
                e_context.action = EventAction.BREAK_PASS
            return
            
        if content == "#跳过":
            if session_id in self.current_games:
                game = self.current_games[session_id]
                self.add_score(session_id, -2)  # 跳过扣2分
                score = self.get_score(session_id)
                
                if game["current_index"] < 2:  # 还有下一题
                    game["current_index"] += 1
                    next_question = game["questions"][game["current_index"]]
                    
                    # 发送跳过提示和下一题
                    skip_reply = Reply(ReplyType.TEXT, f"-2分！当前积分：{score}")
                    img_path = os.path.join(os.path.dirname(__file__), "images", next_question["image"])
                    next_reply = Reply(ReplyType.IMAGE_PATH, img_path)
                    info_reply = Reply(ReplyType.TEXT, f"第{game['current_index']+1}题/共3题")
                    e_context['reply'] = [skip_reply, next_reply, info_reply]
                else:  # 最后一题跳过，结束游戏
                    reply = Reply(ReplyType.TEXT, 
                        f"-2分！当前积分：{score}\n"
                        f"\n本轮游戏结束！\n"
                        f"本轮得分：{game['score']}分")
                    del self.current_games[session_id]
                    e_context['reply'] = reply
                
                e_context.action = EventAction.BREAK_PASS
            return