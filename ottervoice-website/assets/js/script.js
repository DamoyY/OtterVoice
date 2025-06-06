/*=============== PARTICLES JS CONFIGURATION ===============*/
particlesJS('particles-js', {
  "particles": {
    "number": {
      "value": 80, // 粒子数量
      "density": {
        "enable": true,
        "value_area": 800
      }
    },
    "color": {
      "value": "#a0aec0" // 粒子颜色 (使用我们的次要文字色)
    },
    "shape": {
      "type": "circle", // 粒子形状
      "stroke": {
        "width": 0,
        "color": "#000000"
      }
    },
    "opacity": {
      "value": 0.3, // 粒子透明度
      "random": true,
      "anim": {
        "enable": true,
        "speed": 1,
        "opacity_min": 0.1,
        "sync": false
      }
    },
    "size": {
      "value": 3, // 粒子大小
      "random": true,
      "anim": {
        "enable": false
      }
    },
    "line_linked": {
      "enable": true,
      "distance": 150, // 连接线距离
      "color": "#a0aec0", // 连接线颜色
      "opacity": 0.2, // 连接线透明度
      "width": 1
    },
    "move": {
      "enable": true,
      "speed": 1.5, // 粒子移动速度
      "direction": "none",
      "random": false,
      "straight": false,
      "out_mode": "out",
      "bounce": false,
      "attract": {
        "enable": false
      }
    }
  },
  "interactivity": {
    "detect_on": "canvas",
    "events": {
      "onhover": {
        "enable": true,
        "mode": "grab" // 鼠标悬停时抓住粒子
      },
      "onclick": {
        "enable": true,
        "mode": "push" // 鼠标点击时推开粒子
      },
      "resize": true
    },
    "modes": {
      "grab": {
        "distance": 140,
        "line_linked": {
          "opacity": 0.5
        }
      },
      "bubble": {
        "distance": 400,
        "size": 40,
        "duration": 2,
        "opacity": 8,
        "speed": 3
      },
      "repulse": {
        "distance": 200,
        "duration": 0.4
      },
      "push": {
        "particles_nb": 4 // 点击时增加的粒子数量
      },
      "remove": {
        "particles_nb": 2
      }
    }
  },
  "retina_detect": true
});


/*=============== AOS INITIALIZATION ===============*/
AOS.init({
    duration: 1000, 
    once: true,    
    offset: 50,     
});