import sys, os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

import streamlit as st
import time

# 不要加 src. 前缀
from app.perception.video_stream import VideoStream
from drivers.tello_sdk import TelloSDK


# ========================
#   全局无人机控制类
# ========================
class DroneController:
    def __init__(self):
        self.sdk = TelloSDK()
        self.log = []
    def send_cmd(self, cmd):
        res = self.sdk.send_command(cmd)
        msg = f"发送: {cmd} → 回应: {res}"
        self.log.append(msg)
        return msg
    def takeoff(self): return self.send_cmd("takeoff")
    def land(self): return self.send_cmd("land")
    def forward(self): return self.send_cmd("forward 30")
    def back(self): return self.send_cmd("back 30")
    def left(self): return self.send_cmd("left 30")
    def right(self): return self.send_cmd("right 30")
    def streamon(self): return self.send_cmd("streamon")
    def streamoff(self): return self.send_cmd("streamoff")
    def close(self): self.sdk.close()

# ========================
#   页面状态与对象初始化
# ========================
if "controller" not in st.session_state:
    st.session_state.controller = DroneController()
controller = st.session_state.controller

if "video_stream" not in st.session_state:
    st.session_state.video_stream = VideoStream()
video_stream = st.session_state.video_stream

if "streaming" not in st.session_state:
    st.session_state.streaming = False

# ========================
#   页面布局
# ========================
st.set_page_config(page_title="无人机Web控制台", layout="wide")
st.title("Tello无人机 Web 控制面板")

with st.sidebar:
    st.header("控制命令")
    if st.button("起飞（takeoff）"): st.success(controller.takeoff())
    if st.button("降落（land）"): st.success(controller.land())
    st.write("---")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("前进"): st.success(controller.forward())
        if st.button("左转"): st.success(controller.left())
    with col2:
        if st.button("后退"): st.success(controller.back())
        if st.button("右转"): st.success(controller.right())
    st.write("---")
    if st.button("开启视频流"):
        st.success(controller.streamon())
        video_stream.start()
        st.session_state.streaming = True
    if st.button("关闭视频流"):
        st.success(controller.streamoff())
        video_stream.stop()
        st.session_state.streaming = False
    if st.button("关闭连接"):
        controller.close()
        st.info("已关闭与无人机的连接")

# ========================
#   视频流显示区
# ========================
if "video_stream" not in st.session_state:
    st.session_state.video_stream = VideoStream()

video_stream = st.session_state.video_stream

if st.button("启动视频流"):
    video_stream.start()
    st.success("视频流已启动")

frame = video_stream.get_frame()
if frame is not None:
    st.image(frame, channels="BGR")


# ===== 可选：自动刷新（流畅！） =====
from streamlit_autorefresh import st_autorefresh
st_autorefresh(interval=100)  # 100ms自动刷新

# ========================
#   日志显示
# ========================
st.subheader("控制日志")
if controller.log:
    st.write('\n'.join(controller.log[-20:]))  # 显示最近20条
