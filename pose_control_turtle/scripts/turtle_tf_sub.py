#!/usr/bin/env python
# coding=utf-8
import rospy
import tf2_ros
from geometry_msgs.msg import TransformStamped, Twist
import math

if __name__ == "__main__":
    # 2.初始化 ros 节点
    rospy.init_node("sub_tfs_p")
    # 3.创建 TF 订阅对象
    buffer = tf2_ros.Buffer()
    listener = tf2_ros.TransformListener(buffer)
    # 4.处理订阅到的 TF
    rate = rospy.Rate(10)
    # 创建速度发布对象
    pub = rospy.Publisher("/turtle2/cmd_vel",Twist,queue_size=1000)
    while not rospy.is_shutdown():

        rate.sleep()
        try:
            #def lookup_transform(self, target_frame, source_frame, time, timeout=rospy.Duration(0.0)):
            trans = buffer.lookup_transform("turtle2","turtle1",rospy.Time(0))
            # rospy.loginfo("相对坐标:(%.2f,%.2f,%.2f)",
            #             trans.transform.translation.x,
            #             trans.transform.translation.y,
            #             trans.transform.translation.z
            #             )   
            # 根据转变后的坐标计算出速度和角速度信息
            twist = Twist()
            # 间距 = x^2 + y^2  然后开方
            twist.linear.x = 0.5 * math.sqrt(math.pow(trans.transform.translation.x,2) + math.pow(trans.transform.translation.y,2))
            twist.angular.z = 4 * math.atan2(trans.transform.translation.y, trans.transform.translation.x)

            pub.publish(twist)

        except Exception as e:
            pass
