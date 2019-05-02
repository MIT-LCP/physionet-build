/*
 *  /MathJax/extensions/a11y/accessibility-menu.js
 *
 *  Copyright (c) 2009-2018 The MathJax Consortium
 *
 *  Licensed under the Apache License, Version 2.0 (the "License");
 *  you may not use this file except in compliance with the License.
 *  You may obtain a copy of the License at
 *
 *      http://www.apache.org/licenses/LICENSE-2.0
 *
 *  Unless required by applicable law or agreed to in writing, software
 *  distributed under the License is distributed on an "AS IS" BASIS,
 *  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 *  See the License for the specific language governing permissions and
 *  limitations under the License.
 */

(function(d,g){var f=d.config.menuSettings;var h,b;var e=(Function.prototype.bind?function(l,k){return l.bind(k)}:function(l,k){return function(){l.apply(k,arguments)}});var i=Object.keys||function(l){var k=[];for(var m in l){if(l.hasOwnProperty(m)){k.push(m)}}return k};var j=MathJax.Ajax.config.path;if(!j.a11y){j.a11y=d.config.root+"/extensions/a11y"}var a=g["accessibility-menu"]={version:"1.4.0",prefix:"",defaults:{},modules:[],MakeOption:function(k){return a.prefix+k},GetOption:function(k){return f[a.MakeOption(k)]},AddDefaults:function(){var n=i(a.defaults);for(var l=0,k;k=n[l];l++){var m=a.MakeOption(k);if(typeof(f[m])==="undefined"){f[m]=a.defaults[k]}}},AddMenu:function(){var l=Array(this.modules.length);for(var n=0,m;m=this.modules[n];n++){l[n]=m.placeHolder}var p=b.FindId("Accessibility");if(p){l.unshift(h.RULE());p.submenu.items.push.apply(p.submenu.items,l)}else{var o=(b.FindId("Settings","Renderer")||{}).submenu;if(o){l.unshift(h.RULE());l.unshift(o.items.pop());l.unshift(o.items.pop())}l.unshift("Accessibility");var p=h.SUBMENU.apply(h.SUBMENU,l);var k=b.IndexOfId("Locale");if(k){b.items.splice(k,0,p)}else{b.items.push(h.RULE(),p)}}},Register:function(k){a.defaults[k.option]=false;a.modules.push(k)},Startup:function(){h=MathJax.Menu.ITEM;b=MathJax.Menu.menu;for(var l=0,k;k=this.modules[l];l++){k.CreateMenu()}this.AddMenu()},LoadExtensions:function(){var m=[];for(var l=0,k;k=this.modules[l];l++){if(f[k.option]){m.push(k.module)}}return(m.length?d.Startup.loadArray(m):null)}};var c=MathJax.Extension.ModuleLoader=MathJax.Object.Subclass({option:"",name:["",""],module:"",placeHolder:null,submenu:false,extension:null,Init:function(n,k,l,o,m){this.option=n;this.name=[k.replace(/ /g,""),k];this.module=l;this.extension=o;this.submenu=(m||false)},CreateMenu:function(){var k=e(this.Load,this);if(this.submenu){this.placeHolder=h.SUBMENU(this.name,h.CHECKBOX(["Activate","Activate"],a.MakeOption(this.option),{action:k}),h.RULE(),h.COMMAND(["OptionsWhenActive","(Options when Active)"],null,{disabled:true}))}else{this.placeHolder=h.CHECKBOX(this.name,a.MakeOption(this.option),{action:k})}},Load:function(){d.Queue(["Require",MathJax.Ajax,this.module,["Enable",this]])},Enable:function(k){var l=MathJax.Extension[this.extension];if(l){l.Enable(true,true);MathJax.Menu.saveCookie()}}});a.Register(c("collapsible","Collapsible Math","[a11y]/collapsible.js","collapsible"));a.Register(c("autocollapse","Auto Collapse","[a11y]/auto-collapse.js","auto-collapse"));a.Register(c("explorer","Explorer","[a11y]/explorer.js","explorer",true));a.AddDefaults();d.Register.StartupHook("End Extensions",function(){d.Register.StartupHook("MathMenu Ready",function(){a.Startup();d.Startup.signal.Post("Accessibility Menu Ready")},5)},5);MathJax.Hub.Register.StartupHook("End Cookie",function(){MathJax.Callback.Queue(["LoadExtensions",a],["loadComplete",MathJax.Ajax,"[a11y]/accessibility-menu.js"])})})(MathJax.Hub,MathJax.Extension);
