from typing import Union
from bridge.context import ContextType
from bridge.reply import Reply, ReplyType
from plugins import Plugin, Event, EventContext, EventAction
from common.log import logger
import os
import json
import random
from apscheduler.schedulers.background import BackgroundScheduler
from .config import GAME_CONFIG

@register(
    name="idiom_game",
    desc="看图猜成语小游戏",
    version="1.0",
    author="lanvent",
    desire_priority=100
)
class IdiomGame(Plugin):
    def __init__(self):
        super().__init__()
        self.handlers[Event.ON_HANDLE_CONTEXT] = self.on_handle_context
        
        # 使用配置
        try:
            self._init_data()
            self._init_scheduler()
            logger.info("[IdiomGame] Plugin initialized successfully")
        except Exception as e:
            logger.error(f"[IdiomGame] Plugin initialization failed: {e}")
            raise e

    def _init_data(self):
        """初始化数据文件"""
        self.curdir = os.path.dirname(__file__)
        
        # 加载题库
        self.questions = self._load_json("questions.json").get("questions", [])
        if not self.questions:
            raise ValueError("题库加载失败或为空")
            
        # 加载积分和用户名
        self.scores = self._load_json("scores.json")
        self.usernames = self._load_json("usernames.json")
        
        # 游戏状态
        self.current_games = {}
        self.is_daily_game_time = False

    def _init_scheduler(self):
        """初始化定时任务"""
        self.scheduler = BackgroundScheduler()
        # 使用配置中的时间
        start_time = GAME_CONFIG["daily_game_start"].split(":")
        end_time = GAME_CONFIG["daily_game_end"].split(":")
        
        self.scheduler.add_job(self._start_daily_game, 'cron', 
                             hour=int(start_time[0]), 
                             minute=int(start_time[1]))
        self.scheduler.add_job(self._end_daily_game, 'cron', 
                             hour=int(end_time[0]), 
                             minute=int(end_time[1]))
        self.scheduler.start()

    def _load_json(self, filename: str) -> dict:
        """加载JSON文件"""
        try:
            filepath = os.path.join(self.curdir, filename)
            if os.path.exists(filepath):
                with open(filepath, "r", encoding="utf-8") as f:
                    return json.load(f)
            return {}
        except Exception as e:
            logger.warn(f"[IdiomGame] Failed to load {filename}: {e}")
            return {}

    def _save_json(self, data: dict, filename: str):
        """保存JSON文件"""
        try:
            filepath = os.path.join(self.curdir, filename)
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
        except Exception as e:
            logger.error(f"[IdiomGame] Failed to save {filename}: {e}")

    def _start_daily_game(self):
        """开始每日答题"""
        self.is_daily_game_time = True
        logger.info("[IdiomGame] Daily game started")

    def _end_daily_game(self):
        """结束每日答题"""
        self.is_daily_game_time = False
        logger.info("[IdiomGame] Daily game ended")

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
        """处理消息"""
        if e_context['context'].type != ContextType.TEXT:
            return

        content = e_context['context'].content.strip()
        session_id = e_context['context'].session_id
        
        try:
            # 更新用户昵称
            username = e_context['context'].kwargs.get('msg', {}).get('actual_user_nickname', "未知用户")
            self._update_username(session_id, username)
            
            # 处理命令
            if result := self._process_command(content, session_id):
                e_context['reply'] = result
                e_context.action = EventAction.BREAK_PASS
                
        except Exception as e:
            logger.error(f"[IdiomGame] Error handling message: {e}")
            e_context['reply'] = Reply(ReplyType.TEXT, "处理消息时出现错误，请稍后再试")
            e_context.action = EventAction.BREAK_PASS

    def _process_command(self, content: str, session_id: str):
        """处理游戏命令"""
        # 处理排行榜命令
        if content == "#排行":
            return self._handle_rank_command()
            
        # 处理积分查询命令
        if content == "#积分":
            return self._handle_score_command(session_id)
            
        # 处理开始游戏命令
        if content == "#猜成语":
            return self._handle_start_command(session_id)
            
        # 处理答案命令
        if content.startswith("#答案 "):
            return self._handle_answer_command(session_id, content[3:].strip())
            
        # 处理结束游戏命令
        if content == "#结束":
            return self._handle_end_command(session_id)
            
        # 处理跳过命令
        if content == "#跳过":
            return self._handle_skip_command(session_id)

    def _update_username(self, session_id: str, username: str):
        """更新用户昵称"""
        if session_id not in self.usernames or self.usernames[session_id] != username:
            self.usernames[session_id] = username
            self._save_json(self.usernames, "usernames.json")

    def _add_score(self, session_id: str, points: int):
        """增加积分"""
        if not self.is_daily_game_time:
            logger.debug(f"[IdiomGame] Not in daily game time, score not added")
            return
            
        if session_id not in self.scores:
            self.scores[session_id] = 0
        self.scores[session_id] += points
        self._save_json(self.scores, "scores.json")
        logger.info(f"[IdiomGame] User {session_id} score updated: {points}")

    def _get_random_questions(self, count: int = 3) -> list:
        """获取随机题目"""
        count = min(count, GAME_CONFIG["questions_per_round"])
        return random.sample(self.questions, count)

    def _get_top_players(self, limit: int = 10) -> list:
        """获取积分排行榜"""
        sorted_scores = sorted(self.scores.items(), key=lambda x: x[1], reverse=True)
        top_n = sorted_scores[:limit]
        return [(self.usernames.get(sid, "未知用户"), score) for sid, score in top_n]

    def _handle_rank_command(self) -> Reply:
        """处理排行榜命令"""
        top_players = self._get_top_players()
        if not top_players:
            return Reply(ReplyType.TEXT, "暂无排行数据")
            
        rank_text = "🏆 积分排行榜 TOP10\n\n"
        medals = ["🥇", "🥈", "🥉"]
        for i, (name, score) in enumerate(top_players, 1):
            prefix = medals[i-1] if i <= 3 else "  "
            rank_text += f"{prefix} 第{i}名: {name} - {score}分\n"
        return Reply(ReplyType.TEXT, rank_text)

    def _handle_score_command(self, session_id: str) -> Reply:
        """处理积分查询命令"""
        score = self.scores.get(session_id, 0)
        sorted_scores = sorted(self.scores.items(), key=lambda x: x[1], reverse=True)
        rank = next((i for i, (sid, _) in enumerate(sorted_scores, 1) if sid == session_id), 0)
        
        reply_text = f"您当前的积分是：{score}\n"
        reply_text += f"当前排名：第{rank}名" if rank > 0 else "暂无排名"
        return Reply(ReplyType.TEXT, reply_text)

    def _handle_start_command(self, session_id: str) -> list:
        """处理开始游戏命令"""
        if len(self.questions) < GAME_CONFIG["questions_per_round"]:
            return Reply(ReplyType.TEXT, "题库加载失败,无法开始游戏")
            
        if session_id in self.current_games:
            return Reply(ReplyType.TEXT, "您已经在游戏中了,请先完成当前题目或输入 #结束 结束游戏")
            
        # 获取随机题目并初始化游戏状态
        round_questions = self._get_random_questions(GAME_CONFIG["questions_per_round"])
        self.current_games[session_id] = {
            "questions": round_questions,
            "current_index": 0,
            "score": 0
        }
        
        # 准备第一题
        question = round_questions[0]
        img_path = os.path.join(self.curdir, "images", question["image"])
        
        # 返回图片和状态信息
        status_text = f"第1题/共{GAME_CONFIG['questions_per_round']}题 (每日答题时间，答题将计分)" if self.is_daily_game_time else f"第1题/共{GAME_CONFIG['questions_per_round']}题 (非答题时间，答题不计分)"
        return [
            Reply(ReplyType.IMAGE_PATH, img_path),
            Reply(ReplyType.TEXT, status_text)
        ]

    def _handle_answer_command(self, session_id: str, answer: str) -> Union[Reply, list]:
        """处理答案命令"""
        try:
            if session_id not in self.current_games:
                return Reply(ReplyType.TEXT, "当前没有进行中的游戏,请先使用 #猜成语 开始游戏")
            
            game = self.current_games[session_id]
            current_question = game["questions"][game["current_index"]]
            
            if answer != current_question["answer"]:
                return Reply(ReplyType.TEXT, "答案不对,再想想~")
            
            # 答对了，处理积分
            self._add_score(session_id, GAME_CONFIG["correct_score"])
            game["score"] += GAME_CONFIG["correct_score"]
            score = self.scores.get(session_id, 0)
            
            # 如果还有下一题
            if game["current_index"] < GAME_CONFIG["questions_per_round"] - 1:
                game["current_index"] += 1
                next_question = game["questions"][game["current_index"]]
                img_path = os.path.join(self.curdir, "images", next_question["image"])
                
                return [
                    Reply(ReplyType.TEXT, f"恭喜你答对了! 答案就是: {answer}\n+{GAME_CONFIG['correct_score']}分！当前积分：{score}"),
                    Reply(ReplyType.IMAGE_PATH, img_path),
                    Reply(ReplyType.TEXT, f"第{game['current_index']+1}题/共{GAME_CONFIG['questions_per_round']}题")
                ]
                
            # 最后一题答对，结束游戏
            result = (f"恭喜你答对了! 答案就是: {answer}\n"
                     f"+{GAME_CONFIG['correct_score']}分！当前积分：{score}\n"
                     f"\n本轮游戏结束！\n"
                     f"本轮得分：{game['score']}分")
            del self.current_games[session_id]
            return Reply(ReplyType.TEXT, result)
        except Exception as e:
            logger.error(f"[IdiomGame] Error handling answer command: {e}")
            return Reply(ReplyType.TEXT, "处理答案时出现错误，请稍后再试")

    def _handle_end_command(self, session_id: str) -> Reply:
        """处理结束游戏命令"""
        if session_id not in self.current_games:
            return None
            
        game = self.current_games[session_id]
        current_question = game["questions"][game["current_index"]]
        result = (f"游戏结束,当前题目答案是: {current_question['answer']}\n"
                 f"本轮得分：{game['score']}分")
        del self.current_games[session_id]
        return Reply(ReplyType.TEXT, result)

    def _handle_skip_command(self, session_id: str) -> Union[Reply, list]:
        """处理跳过命令"""
        if session_id not in self.current_games:
            return None
            
        game = self.current_games[session_id]
        self._add_score(session_id, GAME_CONFIG["skip_score"])
        score = self.scores.get(session_id, 0)
        
        # 如果还有下一题
        if game["current_index"] < GAME_CONFIG["questions_per_round"] - 1:
            game["current_index"] += 1
            next_question = game["questions"][game["current_index"]]
            img_path = os.path.join(self.curdir, "images", next_question["image"])
            
            return [
                Reply(ReplyType.TEXT, f"{GAME_CONFIG['skip_score']}分！当前积分：{score}"),
                Reply(ReplyType.IMAGE_PATH, img_path),
                Reply(ReplyType.TEXT, f"第{game['current_index']+1}题/共{GAME_CONFIG['questions_per_round']}题")
            ]
            
        # 最后一题跳过，结束游戏
        result = (f"{GAME_CONFIG['skip_score']}分！当前积分：{score}\n"
                 f"\n本轮游戏结束！\n"
                 f"本轮得分：{game['score']}分")
        del self.current_games[session_id]
        return Reply(ReplyType.TEXT, result)
