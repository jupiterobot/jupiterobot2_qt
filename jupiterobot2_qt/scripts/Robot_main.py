#! /usr/bin/env python
# -*- coding:utf-8 -*-

import sys
from PyQt5.QtWidgets import QApplication, QMainWindow
from PyQt5.QtGui import QImage, QPixmap
from cmds import *
import threading
from pathlib import Path
import signal
import rospy
import pygame
from std_msgs.msg import String
from sensor_msgs.msg import Image
from cv_bridge import CvBridge, CvBridgeError
import cv2

script_dir = os.path.dirname(os.path.realpath(__file__))  # 获取当前脚本所在的目录
model_path = os.path.join(script_dir)  # 构建模型路径

ui_file = model_path+"/Ui_Robot.py"
with open(ui_file, "r", encoding="utf-8") as f:
    content = f.read()
content = content.replace("import imgs_rc", "import imgs.imgs_rc")
with open(ui_file, "w", encoding="utf-8") as f:
    f.write(content)

import xf_tts
import tts_qwen
from Ui_Robot import Ui_MainWindow
from PyQt5.QtCore import QTimer, pyqtSignal, QThread

class PlayThread(QThread):
    finished = pyqtSignal()

    def __init__(self, audio_path, parent=None):
        super().__init__(parent)
        self.audio_path = audio_path
        self.stop_flag = False

    def run(self):
        if not os.path.exists(self.audio_path):
            print("Audio file not found")
            self.finished.emit()
            return

        pygame.mixer.init()
        pygame.mixer.music.load(self.audio_path)
        pygame.mixer.music.play()

        while pygame.mixer.music.get_busy():
            time.sleep(0.2)
            if self.stop_flag:
                pygame.mixer.music.stop()
                break

        self.finished.emit()

    def stop(self):
        self.stop_flag = True


class Main_window(Ui_MainWindow, QMainWindow):
    image_signal = pyqtSignal(object)
    def __init__(self, parent=None):
        super(Main_window, self).__init__(parent)
        self.initui()
        rospy.Subscriber("/qwen_out_question", String, self.update_qwen_question_label, queue_size=10)
        rospy.Subscriber("/qwen_out", String, self.update_qwen_label, queue_size=10)
        rospy.Subscriber("/qwen_tts_result", String, self.play_qwen_result, queue_size=10)
        rospy.Subscriber("/qwen_img_out_question", String, self.update_qwen_img_question_label, queue_size=10)
        rospy.Subscriber("/qwen_img_out", String, self.update_qwen_img_label, queue_size=10)
        rospy.Subscriber("/qwen_img_tts_result", String, self.play_img_result, queue_size=10)

        self.start_camera()
        self.image_signal.connect(self.update_image_label)

        self.qwen_play.setEnabled(False)
        self.qwen_img_play.setEnabled(False)

        # self.arm_show.setFixedSize(1920, 1080)  # 设置为你想要的分辨率
        # 初始化视频播放相关变量
        pkg_path = str(Path(__file__).resolve().parents[1])
        self.cap_arm = cv2.VideoCapture(pkg_path+"/resource/jupiter2_sim_arm_show.mp4")
        self.cap_nav = cv2.VideoCapture(pkg_path+"/resource/jupiter2_sim_nav_show.mp4")
        if not self.cap_arm.isOpened() or not self.cap_nav.isOpened():
            print("Video file not found")
            return
        
        self.arm_timer = QTimer()
        self.arm_timer.timeout.connect(self.update_frame_arm)
        self.nav_timer = QTimer()
        self.nav_timer.timeout.connect(self.update_frame_nav)

        self.is_playing = False
        self.play_thread = None

        # 视频帧率
        self.arm_fps = int(self.cap_arm.get(cv2.CAP_PROP_FPS)) or 25
        self.arm_timer_interval = int(1000 / self.arm_fps)

        self.nav_fps = int(self.cap_nav.get(cv2.CAP_PROP_FPS)) or 25
        self.nav_timer_interval = int(1000 / self.nav_fps)

    def arm_reset(self):
        self.cap_arm.set(cv2.CAP_PROP_POS_FRAMES, 0)
        self.arm_timer.start(self.arm_timer_interval)
        self.arm_play_stop.setText("❚❚")
        self.nav_timer.stop()

    def nav_reset(self):
        self.cap_nav.set(cv2.CAP_PROP_POS_FRAMES, 0)
        self.nav_timer.start(self.nav_timer_interval)
        self.nav_play_stop.setText("❚❚")
        self.arm_timer.stop()


    def arm_play_pause(self):
        if self.arm_timer.isActive():
            self.arm_timer.stop()
            self.arm_play_stop.setText("▶")  # 改变按钮文本为“播放”
        else:
            self.arm_timer.start(self.arm_timer_interval)
            self.arm_play_stop.setText("❚❚")  # 改变按钮文本为“暂停”


    def nav_play_pause(self):
        if self.nav_timer.isActive():
            self.nav_timer.stop()
            self.nav_play_stop.setText("▶")  # 改变按钮文本为“播放”
        else:
            self.nav_timer.start(self.nav_timer_interval)
            self.nav_play_stop.setText("❚❚")  # 改变按钮文本为“暂停”

    def update_frame_arm(self):
        ret, frame = self.cap_arm.read()
        if ret:
            # 将 BGR 转换为 RGB
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            h, w, ch = frame_rgb.shape
            bytes_per_line = ch * w
            qt_image = QImage(frame_rgb.data, w, h, bytes_per_line, QImage.Format_RGB888)
            pixmap = QPixmap.fromImage(qt_image).scaled(self.arm_show.size(), aspectRatioMode=True)
            self.arm_show.setPixmap(pixmap)
        else:
            self.arm_timer.stop()
            self.arm_play_stop.setText("▶")
            self.cap_arm.set(cv2.CAP_PROP_POS_FRAMES, 0)  # 回到开头

    def update_frame_nav(self):
        ret, frame = self.cap_nav.read()
        if ret:
            # 将 BGR 转换为 RGB
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            h, w, ch = frame_rgb.shape
            bytes_per_line = ch * w
            qt_image = QImage(frame_rgb.data, w, h, bytes_per_line, QImage.Format_RGB888)
            pixmap = QPixmap.fromImage(qt_image).scaled(self.nav_show.size(), aspectRatioMode=True)
            self.nav_show.setPixmap(pixmap)
        else:
            self.nav_timer.stop()
            self.nav_play_stop.setText("▶")
            self.cap_nav.set(cv2.CAP_PROP_POS_FRAMES, 0)  # 回到开头

    def qwen_chat_in(self):
        self.qwen_play.setEnabled(False)
        self.qwen_play.setText("Waiting for result...")
        if self.is_playing:
            self.stop_playback(1)
        QTimer.singleShot(1000, lambda: self.qwen_out.setText("Listerning..."))
        qwen_in()

    def qwen_img_in1(self):
        self.qwen_img_play.setEnabled(False)
        self.qwen_img_play.setText("Waiting for result...")
        if self.is_playing:
            self.stop_playback(2)
        QTimer.singleShot(1000, lambda: self.qwen_img_out.setText("Listerning..."))
        qwen_img_in()

    def update_qwen_label(self,msg):
        if msg.data:
            current_text = self.qwen_out.text()
            new_text = current_text + msg.data 
            self.qwen_out.setText(new_text)

    def update_qwen_img_label(self,msg):
        if msg.data:
            current_text = self.qwen_img_out.text()
            new_text = current_text + msg.data
            self.qwen_img_out.setText(new_text)

    def update_qwen_question_label(self,msg):
        if msg.data:
            new_text = '=== Question ===\n'+msg.data 
            self.qwen_out.setText(new_text)

    def update_qwen_img_question_label(self,msg):
        if msg.data:
            new_text = msg.data
            self.qwen_img_out.setText(new_text)

    def play_qwen_result(self, msg):
        mp3_file = msg.data

        if mp3_file:
            self.qwen_play.setEnabled(True)
            print("\n=== Start Playback ===\n")
            self.start_playback(mp3_file, num=1)
        else:
            print("\n=== Audio not found ===\n")

    def play_img_result(self, msg):
        mp3_file = msg.data 

        if mp3_file:
            self.qwen_img_play.setEnabled(True)
            print("\n=== Start Playback ===\n")
            self.start_playback(mp3_file, num=2)
        else:
            print("\n===Audio not found===\n")


    def start_playback(self, file_path, num):

        self.play_thread = PlayThread(file_path)
        self.play_thread.finished.connect(lambda: self.on_play_finished(num))
        self.play_thread.start()
        self.is_playing = True
        if num == 1:
            self.qwen_play.setText("❚❚")
        else:
            self.qwen_img_play.setText("❚❚")

    def on_play_finished(self, num):
        self.is_playing = False
        if num == 1:
            self.qwen_play.setText("▶")
        else:
            self.qwen_img_play.setText("▶")


    def stop_playback(self, num):
        if self.play_thread and self.play_thread.isRunning():
            self.play_thread.stop()
            self.play_thread.wait()
        self.on_play_finished(num=num)

    # 初始化样式
    def initui(self):
        self.setupUi(self)
        self.setWindowTitle('JupiterRobot')
        self.sub_iat = None   # 初始化为 None，表示尚未创建订阅
        self.is_recording = False  # 防止重复触发标志
        self.bridge = CvBridge()
        self.pushbutton_manager()
        self.stackedWidget.setCurrentIndex(4)
        self.stackedWidget_2.setCurrentIndex(0)
        self.O5.setStyleSheet("background-color:#f8f7f0;color:#006699;")
        self.camera_s = False  # 摄像头状态
        self.last_image_time = rospy.Time.now()  # 最后一次收到图像的时间

        self.allow_close = False

    def closeEvent(self, event):
        """
        重写 closeEvent：防止窗口被关闭
        """
        if not self.allow_close:
            print("Press Ctrl+C to close terminal")
            event.ignore()  # 忽略关闭事件，窗口不会消失
            if not self.isFullScreen():
                self.showFullScreen()
        else:
            event.accept()  # 允许关闭

    def reading(self, num):
        # 设置高亮颜色
        self.label_5.setStyleSheet("color: #006699;")

        if num==1:
            img_follow()
            duration = 4000
        elif num==2:
            yolo_1()
            duration = 20000
            self.label_13.setStyleSheet("color: #006699;")
            QTimer.singleShot(15000, lambda: self.label_13.setStyleSheet(f"background-color: #f8f7f0;"))
        elif num==3:
            face_jc()
            duration = 6000
        elif num==4:
            med_2()
            duration = 6000
        elif num==5:
            med_3()
            duration = 6000
        elif num==6:
            med_4()
            duration = 6000
        elif num==7:
            med_1()
            duration = 6000
        elif num==8:
            face_sb()
            duration = 6000
        QTimer.singleShot(duration, lambda: self.label_5.setStyleSheet(f"background-color: #f8f7f0;"))
            

    def gesture_takephoto(self):
        stop_ros_node("/mediapipe_demo")
        stop_ros_node("/pose_control_turtle")
        stop_ros_node("/tf_pub1")
        stop_ros_node("/tf_pub2")
        stop_ros_node("/tf_sub2")
        stop_ros_node("/turtle")
        stop_ros_node("/gesture_photograph_node")
        self.label_7.setStyleSheet("color: #006699;")
        QTimer.singleShot(4000, lambda: self.label_7.setStyleSheet(f"background-color: #f8f7f0;"))
        handpic()

    def pose_control_turtle(self):
        stop_ros_node("/mediapipe_demo")
        stop_ros_node("/pose_control_turtle")
        stop_ros_node("/tf_pub1")
        stop_ros_node("/tf_pub2")
        stop_ros_node("/tf_sub2")
        stop_ros_node("/turtle")
        stop_ros_node("/gesture_photograph_node")
        self.label_7.setStyleSheet("color: #006699;")
        QTimer.singleShot(4000, lambda: self.label_7.setStyleSheet(f"background-color: #f8f7f0;"))
        pose_turtle()

    def space(self, num):
        if num != 3:
            stop_ros_node("/camshift")
            stop_ros_node("/object_detection")
            stop_ros_node("/mediapipe_demo")
        if num != 6:
            stop_ros_node("/gesture_photograph_node")
            stop_ros_node("/mediapipe_demo")
            stop_ros_node("/pose_control_turtle")
            stop_ros_node("/tf_pub1")
            stop_ros_node("/tf_pub2")
            stop_ros_node("/tf_sub2")
            stop_ros_node("/turtle")
        
        self.O1.setStyleSheet("background-color:#006699;border: 0px;")
        self.O2.setStyleSheet("background-color:#006699;border: 0px;")
        self.O3.setStyleSheet("background-color:#006699;border: 0px;")
        self.O5.setStyleSheet("background-color:#006699;border: 0px;")
        self.O6.setStyleSheet("background-color:#006699;border: 0px;")
        self.O7.setStyleSheet("background-color:#006699;border: 0px;")
        self.stop_camera()
        
        if num == 1:
            self.stackedWidget.setCurrentIndex(0)
            self.O1.setStyleSheet("background-color:#f8f7f0;color:#006699;border: 2px solid #000000;")
        elif num == 2:
            self.stackedWidget.setCurrentIndex(1)
            self.O2.setStyleSheet("background-color:#f8f7f0;color:#006699;border: 2px solid #000000;")
            self.arm_reset()
        elif num == 3:
            self.stackedWidget.setCurrentIndex(2)
            self.O3.setStyleSheet("background-color:#f8f7f0;color:#006699;border: 2px solid #000000;")
        elif num == 5:
            self.start_camera()
            self.stackedWidget.setCurrentIndex(4)
            self.O5.setStyleSheet("background-color:#f8f7f0;color:#006699;border: 2px solid #000000;")
        elif num == 6:
            self.stackedWidget.setCurrentIndex(5)
            self.O6.setStyleSheet("background-color:#f8f7f0;color:#006699;border: 2px solid #000000;")
        else:
            self.stackedWidget.setCurrentIndex(3)
            self.O7.setStyleSheet("background-color:#f8f7f0;color:#006699;border: 2px solid #000000;")
            self.nav_reset()


    
    def kill_all_terminor(self):
        cmd0 = 'pkill gnome-terminal'
        os.system(f"gnome-terminal -- bash -c \"{cmd0}; exit\"")

    def backspace(self):
        current_text = self.lineEdit.text()
        if len(current_text) > 0:
            new_text = current_text[:-1]
            self.lineEdit.setText(new_text)

    def append_text(self, text):
        current_text = self.lineEdit.text()
        new_text = current_text + text
        self.lineEdit.setText(new_text)

    # 2.1语音合成
    def yyhc(self):
        text1 = self.lineEdit.text()
        xf_tts.tts_main(text1)

    def xf_iat(self):
        if self.is_recording:
            print("Recording in progress, please do not press repeatatively")
            return

        self.is_recording = True
        self.o1_2.setEnabled(False)

        cmd2 = 'source /opt/ros/noetic/setup.bash && source ~/catkin_ws/devel/setup.bash && rostopic pub -1 /voiceWakeup std_msgs/String "data: ``"'
        os.system(f"bash -c '{cmd2}' &")  # No Terminal
        # 在新终端运行命令
        # os.system(f"gnome-terminal --window -e 'bash -c \"{cmd2};\"'")

        # 如果是第一次调用，则创建订阅
        if self.sub_iat is None:
            self.sub_iat = rospy.Subscriber("/iat_result", String, self.update_label_result, queue_size=1)

        self.get_msg = False
        # 延迟显示“录音中...”
        QTimer.singleShot(1000, self.show_processing_message)
        QTimer.singleShot(13000, self.handle_timeout)


    def show_processing_message(self):
        self.label_11.setText("Recording...")

    def update_label_result(self, result):
        self.get_msg = True

        print("Recognition result received:", result.data)  # 调试信息
        if result.data:
            self.label_11.setText(result.data)
        else:
            self.label_11.setText("Recongnition is not successful")

        # 恢复按钮
        self.is_recording = False
        self.o1_2.setEnabled(True)

    def handle_timeout(self):
        if self.get_msg == True:
            return
        else:
            """超时处理：未收到任何语音识别结果"""
            print("Overtime or no result")
            self.label_11.setText("Overtime or no input")

            # 恢复按钮
            self.is_recording = False
            self.o1_2.setEnabled(True)

    def qwen_button(self):
        self.qwen_chat.setStyleSheet("background-color:#f8f7f0;color:#006699;border-top: 2px solid #000000;border-left: 2px solid #000000;border-bottom: 4px solid #2c2b2b;border-right: 4px solid #2c2b2b;")
        self.qwen_img.setStyleSheet("background-color:#006699;color:#f8f7f0;border-top: 1px solid #000000;border-left: 1px solid #000000;border-bottom: 2px solid #2c2b2b;border-right: 2px solid #2c2b2b;")
        self.stackedWidget_2.setCurrentIndex(0)

    def qwen_img_chat(self):
        self.qwen_img.setStyleSheet("background-color:#f8f7f0;color:#006699;border-top: 2px solid #000000;border-left: 2px solid #000000;border-bottom: 4px solid #2c2b2b;border-right: 4px solid #2c2b2b;")
        self.qwen_chat.setStyleSheet("background-color:#006699;color:#f8f7f0;border-top: 1px solid #000000;border-left: 1px solid #000000;border-bottom: 2px solid #2c2b2b;border-right: 2px solid #2c2b2b;")
        self.stackedWidget_2.setCurrentIndex(1)
        

    def toggle_play(self, num):
        if self.is_playing:
            self.stop_playback(num=num)
        else:
            if num == 1:
                if os.path.exists("qwen_result.mp3"):
                    self.start_playback("qwen_result.mp3", 1)
            else:
                if os.path.exists("qwen_img_result.mp3"):
                    self.start_playback("qwen_img_result.mp3", 2)

    def stop_camera(self):
        if hasattr(self, 'subscriber'):
            self.subscriber.unregister()
            del self.subscriber
            self.qwen_img_show.clear()
            self.is_camera_running = False  # 假设你有一个这样的属性来追踪摄像头状态

    def start_camera(self):
        # 如果没有 subscriber 或者已经被注销，则重新创建
        if not hasattr(self, 'subscriber') or self.subscriber is None:
            self.subscriber = self.initialize_subscriber()
            self.is_camera_running = True
        
    def initialize_subscriber(self):
        return rospy.Subscriber("/camera/color/image_raw", Image, self.image_show_in_qt, queue_size=1)

    def image_show_in_qt(self, msg):
        try:
            cv_image = self.bridge.imgmsg_to_cv2(msg, "bgr8")
            self.image_signal.emit(cv_image)
        except CvBridgeError as e:
            print(e)

    def update_image_label(self, cv_image):
        # 获取 QLabel 的当前尺寸
        label_width = self.qwen_img_show.width()
        label_height = self.qwen_img_show.height()

        # 调整图像大小以适应 QLabel 的尺寸
        target_size = (label_width, label_height)
        resized_image = cv2.resize(cv_image, target_size, interpolation=cv2.INTER_AREA)

        height, width, channel = resized_image.shape
        bytes_per_line = 3 * width
        qt_image = QImage(resized_image.data, width, height, bytes_per_line, QImage.Format_RGB888).rgbSwapped()

        pixmap = QPixmap.fromImage(qt_image)
        self.qwen_img_show.setPixmap(pixmap)

    # 给每个按钮绑定对应的方法
    def pushbutton_manager(self):
        self.O1.clicked.connect(lambda: self.space(1))
        self.O2.clicked.connect(lambda: self.space(2))
        self.O3.clicked.connect(lambda: self.space(3))
        self.O5.clicked.connect(lambda: self.space(5))
        self.O6.clicked.connect(lambda: self.space(6))
        self.O7.clicked.connect(lambda: self.space(7))

        self.o1_1.clicked.connect(lambda: threading.Thread(target=self.yyhc, daemon=True).start())

        self.me.clicked.connect(lambda: self.append_text("我"))
        self.you.clicked.connect(lambda: self.append_text("你"))
        self.he.clicked.connect(lambda: self.append_text("他"))
        self.ok.clicked.connect(lambda: self.append_text("好"))
        self.de.clicked.connect(lambda: self.append_text("的"))
        self.ma.clicked.connect(lambda: self.append_text("吗"))
        self.is_2.clicked.connect(lambda: self.append_text("是"))
        self.who.clicked.connect(lambda: self.append_text("谁"))
        self.at.clicked.connect(lambda: self.append_text("在"))
        self.morning.clicked.connect(lambda: self.append_text("早"))
        self.evening.clicked.connect(lambda: self.append_text("晚"))
        self.up.clicked.connect(lambda: self.append_text("上"))
        self.down.clicked.connect(lambda: self.append_text("下"))
        self.noon.clicked.connect(lambda: self.append_text("午"))
        self.and_2.clicked.connect(lambda: self.append_text("和"))
        self.do_2.clicked.connect(lambda: self.append_text("做"))
        self.go.clicked.connect(lambda: self.append_text("去"))
        self.back.clicked.connect(lambda: self.append_text("后"))
        self.right.clicked.connect(lambda: self.append_text("右"))
        self.no.clicked.connect(lambda: self.append_text("不"))
        self.le.clicked.connect(lambda: self.append_text("了"))
        self.them.clicked.connect(lambda: self.append_text("们"))
        self.left.clicked.connect(lambda: self.append_text("左"))
        self.small.clicked.connect(lambda: self.append_text("小"))
        self.big.clicked.connect(lambda: self.append_text("大"))
        self.see.clicked.connect(lambda: self.append_text("看"))
        self.font.clicked.connect(lambda: self.append_text("前"))
        self.please.clicked.connect(lambda: self.append_text("请"))
        self.ward.clicked.connect(lambda: self.append_text("向"))
        self.single.clicked.connect(lambda: self.append_text("个"))
        self.medle.clicked.connect(lambda: self.append_text("中"))
        self.come.clicked.connect(lambda: self.append_text("来"))
        self.but.clicked.connect(lambda: self.append_text("但"))
        self.for_2.clicked.connect(lambda: self.append_text("为"))
        self.bye.clicked.connect(lambda: self.append_text("再见"))
        self.welcome.clicked.connect(lambda: self.append_text("客气"))
        self.what.clicked.connect(lambda: self.append_text("什么"))
        self.where.clicked.connect(lambda: self.append_text("哪里"))
        self.cause.clicked.connect(lambda: self.append_text("因为"))
        self.must.clicked.connect(lambda: self.append_text("必须"))
        self.so.clicked.connect(lambda: self.append_text("所以"))
        self.without.clicked.connect(lambda: self.append_text("没有"))
        self.ganma.clicked.connect(lambda: self.append_text("干嘛"))
        self.thank.clicked.connect(lambda: self.append_text("谢谢"))
        self.tell.clicked.connect(lambda: self.append_text("告诉"))
        self.than.clicked.connect(lambda: self.append_text("然后"))
        self.could.clicked.connect(lambda: self.append_text("可以"))
        self.cando.clicked.connect(lambda: self.append_text("能够"))
        self.know.clicked.connect(lambda: self.append_text("知道"))
        self.result_2.clicked.connect(lambda: self.append_text("结果"))
        self.staff.clicked.connect(lambda: self.append_text("东西"))

        self.dele.clicked.connect(self.backspace)
        self.o1_2.clicked.connect(self.xf_iat)
        self.o3_1.clicked.connect(lambda: self.reading(1))
        self.o3_5.clicked.connect(lambda: self.reading(2))
        self.o3_6_1.clicked.connect(lambda: self.reading(3))
        self.o3_6_2.clicked.connect(lambda: self.reading(4))
        self.o3_6_3.clicked.connect(lambda: self.reading(5))
        self.o3_6_4.clicked.connect(lambda: self.reading(6))
        self.face_real.clicked.connect(lambda: self.reading(7))
        self.face_recongnize.clicked.connect(lambda: self.reading(8))

        self.o6_1.clicked.connect(self.gesture_takephoto)
        self.pose_turlte.clicked.connect(self.pose_control_turtle)
        self.qwen_chat.clicked.connect(self.qwen_button)
        self.qwen_in.clicked.connect(self.qwen_chat_in)
        self.qwen_img_in.clicked.connect(self.qwen_img_in1)
        self.qwen_img.clicked.connect(self.qwen_img_chat)

        self.qwen_play.clicked.connect(lambda: self.toggle_play(1))
        self.qwen_img_play.clicked.connect(lambda: self.toggle_play(2))

        # 设置播放/暂停按钮点击事件
        self.arm_play_stop.clicked.connect(self.arm_play_pause)
        self.nav_play_stop.clicked.connect(self.nav_play_pause)

# style
class QSSLoader:
    def __init__(self):
        pass

    @staticmethod
    def read_qss_file(sytle_file):
        with open(sytle_file, 'r',  encoding='UTF-8') as file:
            return file.read()


def sigint_handler(*args):
    dw.allow_close = True  # 设置允许关闭标志
    dw.close()             # 主动关闭窗口
    sys.exit(0)


if __name__ == '__main__':
    rospy.init_node("jupiterobot2_qt")

    app = QApplication(sys.argv)
    signal.signal(signal.SIGINT, sigint_handler)
    timer = QTimer()
    timer.start(500)
    timer.timeout.connect(lambda: None)
    dw = Main_window()
    dw.showFullScreen()

    style_file = model_path+'/style/style.qss'
    style_sheet = QSSLoader.read_qss_file(style_file)
    dw.setStyleSheet(style_sheet)

    dw.show()

    sys.exit(app.exec_())