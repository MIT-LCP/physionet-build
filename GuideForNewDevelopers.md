# Guide for New Developers



- [1. Summary of Development Setup](#1-summary-of-development-setup)
  - [Save yourself sometime (Please read this note)](#save-yourself-sometime-please-read-this-note)
- [2. Setting up your system for the first time(The tedious way)](#2-setting-up-your-system-for-the-first-timethe-tedious-way)
  - [2.1 MacOS](#21-macos)
    - [2.1.1 Install Homebrew](#211-install-homebrew)
    - [2.1.2 Install Python3](#212-install-python3)
    - [2.1.3 Install Git](#213-install-git)
    - [2.1.4 Install sqlite3](#214-install-sqlite3)
    - [2.1.5 Install VS Code](#215-install-vs-code)
    - [2.1.6 Clone the project locally](#216-clone-the-project-locally)
    - [2.1.7 Install and create virtual environment](#217-install-and-create-virtual-environment)
      - [2.1.7.1 Create a virtual environment](#2171-create-a-virtual-environment)
      - [2.1.7.2 Activate the virtual environment](#2172-activate-the-virtual-environment)
    - [2.1.8 Install requirements](#218-install-requirements)
    - [2.1.9 Run the project](#219-run-the-project)
      - [2.1.9.1 Open a terminal and navigate inside the project directory](#2191-open-a-terminal-and-navigate-inside-the-project-directory)
      - [2.1.9.2 Activate virtual python environment](#2192-activate-virtual-python-environment)
      - [2.1.9.3 Copy .env.example file to .env](#2193-copy-envexample-file-to-env)
      - [2.1.9.4 Run the following commands to set up the database](#2194-run-the-following-commands-to-set-up-the-database)
    - [2.1.10 Start the server (Finally)](#2110-start-the-server-finally)
  - [2.2 Windows](#22-windows)
    - [2.2.1 Install WSL](#221-install-wsl)
    - [2.2.2 Install Python3](#222-install-python3)
    - [2.2.4 Install Git](#224-install-git)
    - [2.2.5 Install sqlite3](#225-install-sqlite3)
    - [2.2.6 Install VS Code](#226-install-vs-code)
    - [2.2.7 Clone the project locally](#227-clone-the-project-locally)
    - [2.2.8 Install and create virtual environment](#228-install-and-create-virtual-environment)
      - [2.2.8.1 Create a virtual environment](#2281-create-a-virtual-environment)
      - [2.2.8.2 Activate the Virtual Environment](#2282-activate-the-virtual-environment)
    - [2.2.9 Install requirements](#229-install-requirements)
    - [2.2.10 Run the project](#2210-run-the-project)
      - [2.2.10.1 Open a Ubuntu terminal and navigate inside the project directory](#22101-open-a-ubuntu-terminal-and-navigate-inside-the-project-directory)
      - [2.2.10.2 Activate virtual python environment.](#22102-activate-virtual-python-environment)
      - [2.2.10.3 Copy .env.example file to .env](#22103-copy-envexample-file-to-env)
      - [2.2.10.4 Run the following commands to set up the database](#22104-run-the-following-commands-to-set-up-the-database)
    - [2.2.11 Start the server (Finally)](#2211-start-the-server-finally)
  - [2.3 Linux](#23-linux)
    - [2.3.1 Install Python3](#231-install-python3)
    - [2.3.2 Install Git](#232-install-git)
    - [2.3.3 Install sqlite3](#233-install-sqlite3)
    - [2.3.4 Install VS Code](#234-install-vs-code)
    - [2.3.5 Clone the project locally](#235-clone-the-project-locally)
    - [2.3.6 Install and create virtual environment](#236-install-and-create-virtual-environment)
      - [2.3.6.1 Create a virtual environment](#2361-create-a-virtual-environment)
      - [2.3.6.2 Activate the Virtual Environment](#2362-activate-the-virtual-environment)
    - [2.3.7 Install requirements](#237-install-requirements)
    - [2.3.8 Run the project](#238-run-the-project)
      - [2.3.8.1 Open a terminal and navigate inside the project directory](#2381-open-a-terminal-and-navigate-inside-the-project-directory)
      - [2.3.8.2 Activate virtual python environment.](#2382-activate-virtual-python-environment)
      - [2.3.8.3 Copy .env.example file to .env](#2383-copy-envexample-file-to-env)
      - [2.3.8.4 Run the following commands to set up the database](#2384-run-the-following-commands-to-set-up-the-database)
    - [2.3.9 Start the server (Finally)](#239-start-the-server-finally)
- [3. Setting up your system for the first time (The Docker Way)](#3-setting-up-your-system-for-the-first-time-the-docker-way)
  - [3.1 MacOS](#31-macos)
    - [3.1.1 Install Homebrew](#311-install-homebrew)
    - [3.1.2 Install Git](#312-install-git)
    - [3.1.3 Install VS Code](#313-install-vs-code)
    - [3.1.4 Clone the project locally](#314-clone-the-project-locally)
    - [3.1.5 Install Docker](#315-install-docker)
    - [3.1.6 Build and run the project](#316-build-and-run-the-project)
      - [3.1.6.1 Open a terminal and navigate inside the project directory](#3161-open-a-terminal-and-navigate-inside-the-project-directory)
      - [3.1.6.2 Copy .env.example file to .env](#3162-copy-envexample-file-to-env)
      - [3.1.6.3 Build the physionet image](#3163-build-the-physionet-image)
      - [3.1.6.4 Start the server and load the demo data](#3164-start-the-server-and-load-the-demo-data)
  - [3.2 Windows](#32-windows)
    - [3.2.1 Install Git Bash](#321-install-git-bash)
    - [3.2.2 Install VS Code](#322-install-vs-code)
    - [3.2.3 Clone the project locally](#323-clone-the-project-locally)
    - [3.2.4 Install Docker](#324-install-docker)
    - [3.2.5 Build and run the project](#325-build-and-run-the-project)
      - [3.2.5.1 Open a CMD and navigate inside the project directory](#3251-open-a-cmd-and-navigate-inside-the-project-directory)
      - [3.2.5.2 Copy .env.example file to .env](#3252-copy-envexample-file-to-env)
      - [3.2.5.3 Build the physionet image](#3253-build-the-physionet-image)
      - [3.2.5.4 Start the server and load the demo data](#3254-start-the-server-and-load-the-demo-data)
  - [3.3 Linux](#33-linux)
    - [3.3.1 Install Git](#331-install-git)
    - [3.3.2 Install VS Code](#332-install-vs-code)
    - [3.3.3 Clone the project locally](#333-clone-the-project-locally)
    - [3.3.4 Install Docker](#334-install-docker)
    - [3.3.5 Build and run the project](#335-build-and-run-the-project)
      - [3.3.5.1 Open a terminal and navigate inside the project directory](#3351-open-a-terminal-and-navigate-inside-the-project-directory)
      - [3.3.5.2 Copy .env.example file to .env](#3352-copy-envexample-file-to-env)
      - [3.3.5.3 Build the physionet image](#3353-build-the-physionet-image)
      - [3.3.5.4 Start the server and load the demo data](#3354-start-the-server-and-load-the-demo-data)
- [Working on new features](#working-on-new-features)



## 1. Summary of Development Setup

The Development Environment setup requires the use of the following tools/software:

1. Package Management System
   1. Mac : [Homebrew](https://brew.sh/)
   2. Windows : [WSL](https://learn.microsoft.com/en-us/windows/wsl/about)(Although this is not a PMS, but we will use to install the tools/software on Windows)
   2. Linux : Yum(Red Hat), [Pacman(Arch)](https://wiki.archlinux.org/title/pacman), [Aptitude(Debian)](https://wiki.debian.org/Aptitude)
2. [Python](https://www.python.org/) - High-level programming language
3. [Git](https://git-scm.com/) - Version control system
4. [SQLITE3](https://www.sqlite.org/index.html) - Database Engine
5. [PostgreSQL](https://www.postgresql.org/) - Relational DBMS
6. [Docker](https://www.docker.com/) -  Software platform that simplifies the process of building, running, managing and distributing applications(Environment Standardization Software)
7. [VS Code](https://code.visualstudio.com/), [Pycharm](https://www.jetbrains.com/pycharm/), [Spyder](https://www.spyder-ide.org/) - Integrated Development Environment - IDE 


### Save yourself sometime (Please read this note)

Before you go ahead and start setting up the development environment, we wanted to let you know that there are two ways you can do the development environment setup.

1. [The docker way](#3-setting-up-your-system-for-the-first-time-the-docker-way) (recommended - This is the easiest way to set up the development environment as it automatically sets up the entire environment for you and takes care of all the installation, also you are less likely to encounter errors)
2. [The tedious way](#2-setting-up-your-system-for-the-first-time) (this can sometimes take long time and be a frustrating experience as you might encounter OS specific challenges during installation of various tools/software)


## 2. Setting up your system for the first time(The tedious way)


### 2.1 MacOS

#### 2.1.1 Install Homebrew

Homebrew is a free and open-source software package management system that simplifies the installation of software on Apple's operating system, MacOS, as well as Linux [source](https://en.wikipedia.org/wiki/homebrew_(package_manager)).

We will use Homebrew to install Python on our Mac. To use Homebrew for Python installation, we need to first install a compiler which we can get by installing Xcode's command-line tools.

To install the xcode, open a terminal on your system, and enter the following command.

```sh
xcode-select --install
```

Now that you have the Xcode's command-line tools installed, let's go ahead and install Homebrew.

To install [Homebrew](https://brew.sh/), paste the following command on your terminal. 

```sh
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/homebrew/install/HEAD/install.sh)"
```
*Note*: Homebrew might need you to use one more command to add Homebrew to your `PATH`, please carefully check if the Homebrew has *NEXT STEPS* for you on the terminal after the installation.


#### 2.1.2 Install Python3

Now that we have Homebrew installed, let's go ahead and install [Python3](https://docs.python-guide.org/starting/install3/osx/).


```sh
brew update
brew install python
```
To confirm that you have Python3 installed and can be accessed, please check this guide from [official python installation for Mac](https://docs.python-guide.org/starting/install3/osx/#working-with-python-3).

In summary, you should be able to access Python3 with the command `python3`. TIP : you can quickly check the Python version by entering the command below on  the terminal

```sh
python3 --version
```

#### 2.1.3 Install Git

Git is free and open-source software for distributed version control. We will use it later to clone the PhysioNet project to our system, and you can also use it to submit your contribution to the project. 
Here are a few resources to learn about Git: [Git official website](https://git-scm.com/book/en/v2/Getting-Started-What-is-Git%3F), [w3schools](https://www.w3schools.com/git/).

```sh
brew install git
```

To verify Git is installed correctly, you can run the following on the terminal.

```sh
git --version
```

#### 2.1.4 Install sqlite3

The physionet-build uses sqlite3 as a quick database for local setup. Let's install that.

```sh
brew install sqlite3
```
#### 2.1.5 Install VS Code

Visual Studio Code is a source-code editor that can be used with a variety of programming languages.


To set VS Code up, you can download it from [official website](https://code.visualstudio.com/) and install it directly on your Mac.

After installing VS Code, you can install this [Python extension on VS Code](https://marketplace.visualstudio.com/items?itemName=ms-python.python) to get the support for IntelliSense (Pylance), Linting, Debugging (multi-threaded, remote), Jupyter Notebooks, code formatting, refactoring, unit tests, and more. 
Simply visit the link above and click on the install button on the website, it should redirect and open the installation option on VS Code.

#### 2.1.6 Clone the project locally

Now that we have the setup, let's go ahead and clone the project to your system. Open a terminal and enter the following command.


```sh
git clone https://github.com/MIT-LCP/physionet-build
```

#### 2.1.7 Install and create virtual environment

Now that we have cloned the project to your system, let's go ahead and create a virtual environment, you can learn more about virtual environments in Python [here](https://realpython.com/python-virtual-environments-a-primer/). 

In Summary, a virtual environment will let us install and keep different versions of the python library specific to individual projects.

Let's create a virtual environment for our project.

##### 2.1.7.1 Create a virtual environment

Open a terminal and enter the following command to navigate inside the project directory.

```sh
cd physionet-build
```
Now create the virtual environment with the following command on the same terminal.
```sh
python3 -m venv env
```

##### 2.1.7.2 Activate the virtual environment

On the same terminal from  step [2.1.7.1](#2171-create-a-virtual-environment), enter the following command to activate the virtual environment.

```sh
source env/bin/activate
```


#### 2.1.8 Install requirements

Now that we have the virtual environment set up, let's install the python libraries needed for the project.

On the same terminal from step [2.1.7.2](#2172-activate-the-virtual-environment), enter the following command to install the requirements.

```sh
pip install -r requirements.txt
```

TIP : If you see an error message about psycopg2-binary, you can open the requirements.txt inside the project directory and remove psycopg2-binary temporarily (and run the `pip install -r requirements.txt` command again). Since we are using sqlite3, psycopg2-binary which is a PostgreSQL database adapter for the Python, is not needed for local development. After you have installed all the requirements, you can add it back to the requirements.txt file.



#### 2.1.9 Run the project
We now have everything set up to run the project locally, let's go ahead and set up the project

##### 2.1.9.1 Open a terminal and navigate inside the project directory

```sh
cd physionet-build
```



##### 2.1.9.2 Activate virtual python environment

```sh
source env/bin/activate
```

##### 2.1.9.3 Copy .env.example file to .env

```sh
cp .env.example .env
```



##### 2.1.9.4 Run the following commands(on the same terminal from [2.1.9.3](#2193-copy-envexample-file-to-env) ) to set up the database and compile the static files.

  - Run : `cd physionet-django` to navigate inside the django project

  - Run : `python3 manage.py resetdb` to reset the database with the latest applied migrations.

  - Run : `python3 manage.py loaddemo` to load the demo fixtures set up example files.
  
  - Run : `python3 manage.py compilestatic` to compile the css files.

#### 2.1.10 Start the server (Finally)

Enter the following command to start the server.

```sh
python3 manage.py runserver
```

The local development server will be available at [http://localhost:8000](http://localhost:8000).


[Back to top](#guide-for-new-developers)


### 2.2 Windows

On Windows, we will use WSL (Windows Subsystem for Linux) to install Python and other dependencies. You can learn more about WSL on the [official website](https://learn.microsoft.com/en-us/windows/wsl/install).

WSL will install Ubuntu on your system by default, and you can use the Ubuntu terminal to install and run the project.

#### 2.2.1 Install WSL

To install WSL, you can follow the [official instructions](https://learn.microsoft.com/en-us/windows/wsl/install).

Please make sure you update the WSL to WSL2, here is the [official guide](https://learn.microsoft.com/en-us/windows/wsl/install#upgrade-version-from-wsl-1-to-wsl-2) on how to upgrade to WSL2.

TIP : If you are not sure what is a CMD, [here](https://www.makeuseof.com/tag/a-beginners-guide-to-the-windows-command-line/) is a read about CMD and how to open it.

TIP: If you get error `0xc03a001a` when updating to WSL2 , please check [this github issue](https://github.com/microsoft/WSL/issues/4299#issuecomment-678650491) on how to fix it.


#### 2.2.2 Install Python3

Now that WSL is installed, let's go ahead and install Python3 on WSL.

*Note: Check if you already have a Python3 installed on your system(if you already have the latest version of Python3, you won't have to do the step 2.2.2), to check enter the following on Ubuntu Terminal.*

Please open the Ubuntu terminal and enter the following command to check if you have Python3 installed on your system.


```cmd
python3 --version
```


On the Ubuntu terminal, enter the following commands to install Python3.


```sh
sudo apt update
sudo apt install software-properties-common gcc build-essential python3-dev python3-venv
```

```sh
sudo add-apt-repository ppa:deadsnakes/ppa
sudo apt update
sudo apt install python3
```


To confirm that you have Python3 installed and can be accessed, please check this guide for [Python installation for Linux](https://docs.python-guide.org/starting/install3/linux/#working-with-python-3).

In summary, you should be able to access Python3 with the command `python3`, you can quickly check the Python version by entering the command below on  the terminal.

```sh
python3 --version
```

#### 2.2.4 Install Git

Git is free and open-source software for distributed version control. We will use it later to clone the PhysioNet project to our system, and you can also use it to submit your contribution to the project. 
Here are a few resources to learn about Git: [Git official website](https://git-scm.com/book/en/v2/Getting-Started-What-is-Git%3F), [w3schools](https://www.w3schools.com/git/).

To install Git on Ubuntu, enter the following command on the Ubuntu terminal.

```sh
sudo apt install git
```

To verify Git is installed correctly, you can run the following in the terminal.

```sh
git --version
```

#### 2.2.5 Install sqlite3

The physionet-build uses sqlite3 as a quick database for local set up. Let's install that.

To install sqlite3 on Ubuntu, enter the following command on the Ubuntu terminal.

```sh
sudo apt install sqlite3
```

#### 2.2.6 Install VS Code

Visual Studio Code is a source-code editor that can be used with a variety of programming languages.

To set VS Code up, you can download the .exe package from [official website](https://code.visualstudio.com/) and install it directly on your Windows by following the [official instructions](https://code.visualstudio.com/docs/setup/windows). 


After installing VS Code, you can install this [Python extension on VS Code](https://marketplace.visualstudio.com/items?itemName=ms-python.python) to get the support for IntelliSense (Pylance), Linting, Debugging (multi-threaded, remote), Jupyter Notebooks, code formatting, refactoring, unit tests, and more. 
Simply visit the link above and click on the install button on the website, it should redirect and open the installation option on VS Code.


#### 2.2.7 Clone the project locally

Now that we have all the setup, let's go ahead and clone the project to your system. Enter the following command on the Ubuntu terminal to clone the project.

```sh
git clone https://github.com/MIT-LCP/physionet-build
```

#### 2.2.8 Install and create virtual environment

Now that we have cloned the project to your system, let's go ahead and create a virtual environment, you can learn more about virtual environments in Python [here](https://realpython.com/python-virtual-environments-a-primer/). 

In Summary, a virtual environment will let us install and keep different versions of the python library specific to individual projects.

Let's create a virtual environment for our project.

##### 2.2.8.1 Create a virtual environment

Open a Ubuntu terminal and enter the following command to navigate inside the project directory.

```sh
cd physionet-build
```
Now create the virtual environment with the following command on the same terminal.
```sh
python3 -m venv env
```

TIP : If you get a message like `python3-venv is not installed` , please run the following command on the terminal and try again.

```sh
sudo apt install python3-venv
```

##### 2.2.8.2 Activate the Virtual Environment

On the same terminal from step [2.2.8.1](#2281-create-a-virtual-environment), enter the following command to activate the virtual environment.

```sh
source env/bin/activate
```


#### 2.2.9 Install requirements

Now that we have the virtual environment set up, let's install the python libraries needed for the project.

On the same terminal from step [2.2.8.2](#2282-activate-the-virtual-environment), enter the following command to install the requirements.

```sh
pip install -r requirements.txt
```

TIP : If you see an error message about psycopg2-binary, you can open the requirements.txt inside the project directory and remove psycopg2-binary temporarily (and run the `pip install -r requirements.txt` command again). Since we are using sqlite3, psycopg2-binary which is a PostgreSQL database adapter for the Python, is not needed for local development. After you have installed all the requirements, you can add it back to the requirements.txt file.

TIP : If you are having difficulty in opening the project in VS Code, you could open a Ubuntu terminal and enter the following command to open the project in VS Code.

```sh
cd physionet-build
code .
```

#### 2.2.10 Run the project

We now have everything set up to run the project locally, let's go ahead and set up the project.

##### 2.2.10.1 Open a Ubuntu terminal and navigate inside the project directory

```sh
cd physionet-build
```


##### 2.2.10.2 Activate virtual python environment.

```sh
source env/bin/activate
```

##### 2.2.10.3 Copy .env.example file to .env

```sh
cp .env.example .env
```


##### 2.2.10.4 Run the following commands(on the same terminal from [2.2.10.3](#22103-copy-envexample-file-to-env)) to set up the database and compile the static files.

  - Run : `cd physionet-django` to navigate inside the django project

  - Run : `python3 manage.py resetdb` to reset the database with the latest applied migrations.

  - Run : `python3 manage.py loaddemo` to load the demo fixtures set up example files.

  - Run : `python3 manage.py compilestatic` to compile the css files.


#### 2.2.11 Start the server (Finally)

Enter the following command to start the server.

```sh
python3 manage.py runserver
```

The local development server will be available at [http://localhost:8000](http://localhost:8000).

[Back to top](#guide-for-new-developers)



### 2.3 Linux


#### 2.3.1 Install Python3

Because Linux has many distros, please follow the guide from [Real Python](https://realpython.com/installing-python/#how-to-install-python-on-linux) to set up Python3 based on your Linux system.

Here we have added instructions on installing Python3 on Ubuntu(Debian-based Linux Distro).

Open a terminal and enter the following commands.

```sh
sudo apt update
sudo apt install software-properties-common gcc build-essential python3-dev python3-venv
```

```sh
sudo add-apt-repository ppa:deadsnakes/ppa
sudo apt update
sudo apt install python3
```


To confirm that you have Python3 installed and can be accessed, please check this guide for [Python installation for Linux](https://docs.python-guide.org/starting/install3/linux/#working-with-python-3).

In summary, you should be able to access Python3 with the command `python3`, you can quickly check the Python version by entering the command below on  the terminal.

```sh
python3 --version
```

#### 2.3.2 Install Git

Git is free and open-source software for distributed version control. We will use it later to clone the PhysioNet project to our system, and you can also use it to submit your contribution to the project. 
Here are a few resources to learn about Git [Git official website](https://git-scm.com/book/en/v2/Getting-Started-What-is-Git%3F), [w3schools](https://www.w3schools.com/git/).

```sh
sudo apt install git
```

To verify Git is installed correctly, you can run the following in the terminal.

```sh
git --version
```

#### 2.3.3 Install sqlite3

The physionet-build uses sqlite3 as a quick database for local set up. Let's install that.

```sh
sudo apt install sqlite3
```

#### 2.3.4 Install VS Code

Visual Studio Code is a source-code editor that can be used with a variety of programming languages.


To set VS Code up, you can download the .deb package from [official website](https://code.visualstudio.com/) and install it directly on your Linux by the following the [official instruction](https://code.visualstudio.com/docs/setup/linux).


```sh
sudo apt install ./<path to your downloaded vscode file>.deb
```

After installing VS Code, you can install this [Python extension on VS Code](https://marketplace.visualstudio.com/items?itemName=ms-python.python) to get the support for IntelliSense (Pylance), Linting, Debugging (multi-threaded, remote), Jupyter Notebooks, code formatting, refactoring, unit tests, and more. 
Simply visit the link above and click on the install button on the website, it should redirect and open the installation option on VS Code.

#### 2.3.5 Clone the project locally

Now that we have the setup, let's go ahead and clone the project to your system. Open a terminal and enter the following command.


```sh
git clone https://github.com/MIT-LCP/physionet-build
```

#### 2.3.6 Install and create virtual environment

Now that we have cloned the project to your system, let's go ahead and create a virtual environment, you can learn more about virtual environments in Python [here](https://realpython.com/python-virtual-environments-a-primer/). 

In Summary, a virtual environment will let us install and keep different versions of the python library specific to individual projects.

Let's create a virtual environment for our project.

##### 2.3.6.1 Create a virtual environment

Open a terminal and enter the following command to navigate inside the project directory.

```sh
cd physionet-build
```
Now create the virtual environment with the following command on the same terminal.
```sh
python3 -m venv env
```


TIP : If you get a message like `python3-venv is not installed` , please run the following command on the terminal and try again.

```sh
sudo apt install python3-venv
```

##### 2.3.6.2 Activate the Virtual Environment

On the same terminal from  step [2.3.6.1](#2361-create-a-virtual-environment), enter the following command to activate the virtual environment.

```sh
source env/bin/activate
```


#### 2.3.7 Install requirements

Now that we have the virtual environment set up, let's install the python libraries needed for the project.

On the same terminal from step [2.3.6.2](#2362-activate-the-virtual-environment), enter the following command to install the requirements.

```sh
pip install -r requirements.txt
```

TIP : If you see an error message about psycopg2-binary, you can open the requirements.txt inside the project directory and remove psycopg2-binary temporarily (and run the `pip install -r requirements.txt` command again). Since we are using sqlite3, psycopg2-binary which is a PostgreSQL database adapter for the Python, is not needed for local development. After you have installed all the requirements, you can add it back to the requirements.txt file.

#### 2.3.8 Run the project

We now have everything set up to run the project locally, let's go ahead and set up the project.

##### 2.3.8.1 Open a terminal and navigate inside the project directory

```sh
cd physionet-build
```



##### 2.3.8.2 Activate virtual python environment.

```sh
source env/bin/activate
```

##### 2.3.8.3 Copy .env.example file to .env

```sh
cp .env.example .env
```


##### 2.3.8.4 Run the following commands(on the same terminal from [2.3.8.3](#2383-copy-envexample-file-to-env) ) to set up the database and compile the static files.

  - Run : `cd physionet-django` to navigate inside the django project

  - Run : `python3 manage.py resetdb` to reset the database with the latest applied migrations.

  - Run : `python3 manage.py loaddemo` to load the demo fixtures set up example files.

  - Run : `python3 manage.py compilestatic` to compile the css files.


#### 2.3.9 Start the server (Finally)

Enter the following command to start the server.

```sh
python3 manage.py runserver
```

The local development server will be available at [http://localhost:8000](http://localhost:8000).

[Back to top](#guide-for-new-developers)







## 3. Setting up your system for the first time (The Docker Way)


### 3.1 MacOS

#### 3.1.1 Install Homebrew

Homebrew is a free and open-source software package management system that simplifies the installation of software on Apple's operating system, MacOS, as well as Linux [source](https://en.wikipedia.org/wiki/homebrew_(package_manager)).

We will use Homebrew to install Git on our Mac. To use Homebrew for Git installation, we need to first install a compiler which we can get by installing Xcode's command-line tools.

To install the xcode, open a terminal on your system, and enter the following command.

```sh
xcode-select --install
```

Now that you have the Xcode's command-line tools installed, let's go ahead and install Homebrew.

To install [Homebrew](https://brew.sh/), paste the following command on your terminal. 

```sh
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/homebrew/install/HEAD/install.sh)"
```
*Note*: Homebrew might need you to use one more command to add Homebrew to your `PATH`, please carefully check if the Homebrew has *NEXT STEPS* for you on the terminal after the installation.



#### 3.1.2 Install Git

Git is free and open-source software for distributed version control. We will use it later to clone the PhysioNet project to our system, and you can also use it to submit your contribution to the project. 
Here are a few resources to learn about Git [Git official website](https://git-scm.com/book/en/v2/Getting-Started-What-is-Git%3F), [w3schools](https://www.w3schools.com/git/).

```sh
brew install git
```

To verify Git is installed correctly, you can run the following in the terminal.

```sh
git --version
```


#### 3.1.3 Install VS Code

Visual Studio Code is a source-code editor that can be used with a variety of programming languages.

To set VS Code up, you can download it from [official website](https://code.visualstudio.com/) and install it directly on your Mac.

After installing VS Code, you can install this [Python extension on VS Code](https://marketplace.visualstudio.com/items?itemName=ms-python.python) to get the support for IntelliSense (Pylance), Linting, Debugging (multi-threaded, remote), Jupyter Notebooks, code formatting, refactoring, unit tests, and more. 
Simply visit the link above and click on the install button on the website, it should redirect and open the installation option on VS Code.

#### 3.1.4 Clone the project locally

Now that we have Git and VS Code set up, let's go ahead and clone the project to your system. Open a terminal and enter the following command.


```sh
git clone https://github.com/MIT-LCP/physionet-build
```

#### 3.1.5 Install Docker

Let's go ahead and install Docker on our system, as promised this will take care of all the setup for us. We are nearly there.

Please follow the [official installation guide](https://docs.docker.com/desktop/install/mac-install/) to install Docker on your Mac.

Here is a recommended read on [Docker](https://www.freecodecamp.org/news/a-beginners-guide-to-docker-how-to-create-your-first-docker-application-cc03de9b639f/).


#### 3.1.6 Build and run the project

Now that we have Docker installed, let's go ahead and build the project. It's as simple as running the following commands in the terminal.


##### 3.1.6.1 Open a terminal and navigate inside the project directory

```sh
cd physionet-build
```

##### 3.1.6.2 Copy .env.example file to .env

```sh
cp .env.example .env
```

##### 3.1.6.3 Build the physionet image
    
```sh
docker-compose build 
```

That should take care of all the setup for you, now let's go ahead start our server and load the demo data on our database.

##### 3.1.6.4 Start the server and load the demo data

To start our server, we can do it with a single command.

```sh
docker-compose up
```

This will start our development server on [http://localhost:8000](http://localhost:8000), run the postgres database, development and test containers. Before you go ahead and play around with the project, we need to load the demo data on our test and development database (Note: we only need to load the demo data when doing the setup for the first time). 

Note: We are using two databases, one for development and the other for testing. The reason for this is to make sure that the test database is always clean and we can run the tests without worrying about the data changes on the  development database.
To do that, we need to open a new terminal and run the following commands.  

Navigate inside the project directory.

```sh
cd physionet-build
```

Enter the development container shell and navigate inside `physionet-django` directory.

```sh
docker-compose exec dev /bin/bash
```
```sh
cd physionet-django
```

Run the following commands to set up the database

  - Run : `python3 manage.py resetdb` to reset the database with the latest applied migrations.

  - Run : `python3 manage.py loaddemo` to load the demo fixtures set up example files.
  
  - Run : `python3 manage.py compilestatic` to compile the css files.


In a new Terminal, enter the test container shell and navigate inside `physionet-django` directory.

```sh
docker-compose exec test /bin/bash
```
```sh
cd physionet-django
```

Run the following commands to set up the database

  - Run : `python3 manage.py resetdb` to reset the database with the latest applied migrations.

  - Run : `python3 manage.py loaddemo` to load the demo fixtures set up example files.


That's it, you are all setup and ready to go. You can now start playing around with the project on [http://localhost:8000](http://localhost:8000).

TIP: If you are trying to login as admin, you can use the forgot password option to reset your password. The email will be printed on the terminal where you started the server.
Simply copy the link from the terminal and paste it in your browser to reset your password and login as admin.



[Back to top](#guide-for-new-developers)


### 3.2 Windows

#### 3.2.1 Install Git Bash
Download Git bash from the [official website](https://git-scm.com/download/win) and install it with the default settings.

Git is free and open-source software for distributed version control. We will use it later to clone the PhysioNet project to our system, and you can also use it to submit your contribution to the project. 
Here are a few resources to learn about Git: [Git official website](https://git-scm.com/book/en/v2/Getting-Started-What-is-Git%3F), [w3schools](https://www.w3schools.com/git/).


#### 3.2.2 Install VS Code

Visual Studio Code is a source-code editor that can be used with a variety of programming languages.

To set VS Code up, you can download the .exe package from [official website](https://code.visualstudio.com/) and install it directly on your Windows by following the [official instructions](https://code.visualstudio.com/docs/setup/windows). 


After installing VS Code, you can install this [Python extension on VS Code](https://marketplace.visualstudio.com/items?itemName=ms-python.python) to get the support for IntelliSense (Pylance), Linting, Debugging (multi-threaded, remote), Jupyter Notebooks, code formatting, refactoring, unit tests, and more. 
Simply visit the link above and click on the install button on the website, it should redirect and open the installation option on VS Code.

#### 3.2.3 Clone the project locally

Now that we have Git Bash and VS Code set up, let's go ahead and clone the project to your system. Open Git bash and enter the following command.


```cmd
git clone https://github.com/MIT-LCP/physionet-build
```


#### 3.2.4 Install Docker

Let's go ahead and install Docker on our system, as promised this will take care of all the setup for us. We are nearly there.

Please follow the [official installation guide](https://docs.docker.com/desktop/install/windows-install/) to install Docker on your Windows.

Here is a recommended read on [Docker](https://www.freecodecamp.org/news/a-beginners-guide-to-docker-how-to-create-your-first-docker-application-cc03de9b639f/).


#### 3.2.5 Build and run the project

Now that we have Docker installed, let's go ahead and build the project. It's as simple as running the following commands in the terminal.


##### 3.2.5.1 Open a CMD and navigate inside the project directory

TIP : If you are not sure what is a CMD, [here](https://www.makeuseof.com/tag/a-beginners-guide-to-the-windows-command-line/) is a read about CMD and how to open it.


```cmd
cd physionet-build
```

##### 3.2.5.2 Copy .env.example file to .env

```cmd
copy .env.example .env
```

##### 3.2.5.3 Build the physionet image
    
```cmd
docker-compose build
```

That should take care of all the setup for you, now let's go ahead start our server and load the demo data on our database.

##### 3.2.5.4 Start the server and load the demo data

To start our server, we can do it with a single command.

```cmd
docker-compose up
```

This will start our development server on [http://localhost:8000](http://localhost:8000), run the postgres database, development and test containers. Before you go ahead and play around with the project, we need to load the demo data on our test and development database (Note: we only need to load the demo data when doing the setup for the first time). 

Note: We are using two databases, one for development and the other for testing. The reason for this is to make sure that the test database is always clean and we can run the tests without worrying about the data changes on the  development database.
To do that, we need to open a new CMD and run the following commands.  

Navigate inside the project directory.

```cmd
cd physionet-build
```

Enter the development container shell and navigate inside `physionet-django` directory.

```cmd
docker-compose exec dev /bin/bash
```

```sh
cd physionet-django
```

Run the following commands to set up the database

  - Run : `python3 manage.py resetdb` to reset the database with the latest applied migrations.

  - Run : `python3 manage.py loaddemo` to load the demo fixtures set up example files.
  
  - Run : `python3 manage.py compilestatic` to compile the css files.


In a new CMD, enter the test container shell and navigate inside `physionet-django` directory.

```cmd
docker-compose exec test /bin/bash
```
```sh
cd physionet-django
```

Run the following commands to set up the database

  - Run : `python3 manage.py resetdb` to reset the database with the latest applied migrations.

  - Run : `python3 manage.py loaddemo` to load the demo fixtures set up example files.


That's it, you are all setup and ready to go. You can now start playing around with the project on [http://localhost:8000](http://localhost:8000).

TIP: If you are trying to login as admin, you can use the forgot password option to reset your password. The email will be printed on the terminal where you started the server.
Simply copy the link from the terminal and paste it in your browser to reset your password and login as admin.




[Back to top](#guide-for-new-developers)



### 3.3 Linux


#### 3.3.1 Install Git

Git is free and open-source software for distributed version control. We will use it later to clone the PhysioNet project to our system, and you can also use it to submit your contribution to the project. 
Here are a few resources to learn about Git [Git official website](https://git-scm.com/book/en/v2/Getting-Started-What-is-Git%3F), [w3schools](https://www.w3schools.com/git/).

```sh
sudo apt install git
```

To verify Git is installed correctly, you can run the following in the terminal.

```sh
git --version
```


#### 3.3.2 Install VS Code

Visual Studio Code is a source-code editor that can be used with a variety of programming languages.


To set VS Code up, you can download the .deb package from [official website](https://code.visualstudio.com/) and install it directly on your Linux by the following the [official instruction](https://code.visualstudio.com/docs/setup/linux).


After installing VS Code, you can install this [Python extension on VS Code](https://marketplace.visualstudio.com/items?itemName=ms-python.python) to get the support for IntelliSense (Pylance), Linting, Debugging (multi-threaded, remote), Jupyter Notebooks, code formatting, refactoring, unit tests, and more. 
Simply visit the link above and click on the install button on the website, it should redirect and open the installation option on VS Code.


#### 3.3.3 Clone the project locally

Now that we have Git and VS Code set up, let's go ahead and clone the project to your system. Open a terminal and enter the following command.


```sh
git clone https://github.com/MIT-LCP/physionet-build
```


#### 3.3.4 Install Docker

Let's go ahead and install Docker on our system, as promised this will take care of all the setup for us. We are nearly there.

Please follow the [official installation guide](https://docs.docker.com/desktop/install/linux-install/) to install Docker on your Linux.

Here is a recommended read on [Docker](https://www.freecodecamp.org/news/a-beginners-guide-to-docker-how-to-create-your-first-docker-application-cc03de9b639f/).


#### 3.3.5 Build and run the project

Now that we have Docker installed, let's go ahead and build the project. It's as simple as running the following commands in the terminal.


##### 3.3.5.1 Open a terminal and navigate inside the project directory

```sh
cd physionet-build
```

##### 3.3.5.2 Copy .env.example file to .env

```sh
cp .env.example .env
```

##### 3.3.5.3 Build the physionet image
    
```sh
docker-compose build 
```

That should take care of all the setup for you, now let's go ahead start our server and load the demo data on our database.

##### 3.3.5.4 Start the server and load the demo data

To start our server, we can do it with a single command.

```sh
docker-compose up
```

This will start our development server on [http://localhost:8000](http://localhost:8000), run the postgres database, development and test containers. Before you go ahead and play around with the project, we need to load the demo data on our test and development database (Note: we only need to load the demo data when doing the setup for the first time). 

Note: We are using two databases, one for development and the other for testing. The reason for this is to make sure that the test database is always clean and we can run the tests without worrying about the data changes on the  development database.
To do that, we need to open a new terminal and run the following commands.  

Navigate inside the project directory.

```sh
cd physionet-build
```

Enter the development container shell and navigate inside `physionet-django` directory.

```sh
docker-compose exec dev /bin/bash
```
```sh
cd physionet-django
```

Run the following commands to set up the database

  - Run : `python3 manage.py resetdb` to reset the database with the latest applied migrations.

  - Run : `python3 manage.py loaddemo` to load the demo fixtures set up example files.
  
  - Run : `python3 manage.py compilestatic` to compile the css files.


In a new terminal, enter the test container shell and navigate inside `physionet-django` directory.

```sh
docker-compose exec test /bin/bash
```
```sh
cd physionet-django
```

Run the following commands to set up the database

  - Run : `python3 manage.py resetdb` to reset the database with the latest applied migrations.

  - Run : `python3 manage.py loaddemo` to load the demo fixtures set up example files.


That's it, you are all setup and ready to go. You can now start playing around with the project on [http://localhost:8000](http://localhost:8000).

TIP: If you are trying to login as admin, you can use the forgot password option to reset your password. The email will be printed on the terminal where you started the server.
Simply copy the link from the terminal and paste it in your browser to reset your password and login as admin.


## Working on new features

Now that you have completed your setup and have familiarized yourself with the codebase, here is how you can contribute and submit your changes for review.

1. Create a new branch for each feature you work on.
2. Work on your changes, add files and commit your changes.
3. On commits, add a clear explanation of the changes. Here is an interesting read from [freeCodeCamp](https://www.freecodecamp.org/news/how-to-write-better-git-commit-messages/) about how to write a good commit message.
4. Once your changes are final and ready to be submitted, push the changes and open a Merge Request. Someone will review your changes ASAP.




Here are some good resources to read about contributing to OpenSource projects, Python and Django.
1. [Making your first Open Source Pull Request | Github](https://www.geeksforgeeks.org/making-first-open-source-pull-request/)
2. [A First Timers Guide to an Open Source Project](https://auth0.com/blog/a-first-timers-guide-to-an-open-source-project/)
3. [Contributing to Open Source : Getting Started](https://www.geeksforgeeks.org/contributing-to-open-source-getting-started)
4. [The (written) unwritten guide to pull requests
](https://www.atlassian.com/blog/git/written-unwritten-guide-pull-requests)
5. [PEP 8 – Style Guide for Python Code](https://peps.python.org/pep-0008/)
6. [Django Documentation](https://docs.djangoproject.com/)
7. [Testing in Django](https://realpython.com/testing-in-django-part-1-best-practices-and-examples/)

